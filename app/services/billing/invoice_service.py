"""Deposit at posting (booked minutes for every seat) and final cost after the shift
(approved minutes). Business pays pay + commission + gateway; rates snapshotted at publish."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.billing.billing_route_strings import (
    INVOICE_KIND_DEPOSIT,
    INVOICE_KIND_FINAL,
    INVOICE_PAID,
    INVOICE_PENDING,
    INVOICE_VOID,
    LINE_GATEWAY_FEE,
    LINE_PLATFORM_FEE,
    LINE_TAX,
    LINE_WORKER_PAY,
    MSG_INVOICE_NOT_FOUND,
    MSG_INVOICE_NOT_READY,
    MSG_INVOICE_SHIFT_STATE,
)
from app.constants.shifts.shift_route_strings import (
    ASG_APPROVED,
    ASG_BOOKED_STATUSES,
    ASG_CHECKED_IN,
    END_WORKER_LEFT,
    MSG_SHIFT_NOT_FOUND,
    SHIFT_COMPLETED,
    SHIFT_FILLED,
    SHIFT_IN_PROGRESS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.repositories.attendance import attendance_repository
from app.repositories.billing import billing_repository
from app.repositories.cancellations import cancellation_repository
from app.repositories.live_work import live_work_repository
from app.repositories.shifts import assignment_repository, shift_repository
from app.schemas.billing.billing_schemas import InvoiceLine, InvoiceResponse
from app.security.authenticated_user import AuthenticatedUser
from app.services.billing.settlement import release_invoice_earnings
from app.services.catalog import catalog_service
from app.services.pricing.pricing_engine import Charge
from app.services.pricing.shift_pricing import as_business_charge, shift_charge
from app.services.profiles.profile_lookup import business_scope
from app.services.promos import promo_service
from app.services.promos.promo_rules import Promo
from app.services.shifts.domain.shift_rules import is_task, paid_minutes, shift_seat_pay
from app.utils.clock import utc_now
from app.utils.money import FeeRates, overtime_pay, pay_for_minutes
from app.utils.references import INVOICE_REFERENCE_PREFIX, new_reference

_INVOICEABLE_SHIFT_STATUSES = (SHIFT_FILLED, SHIFT_IN_PROGRESS, SHIFT_COMPLETED)


async def build_invoice_response(conn: asyncpg.Connection, invoice_id: UUID) -> InvoiceResponse:
    row = await billing_repository.get_invoice(conn, invoice_id)
    lines = await billing_repository.list_invoice_lines(conn, invoice_id)
    data = dict(row)
    for key in (
        "fee_percentage",
        "gateway_fee_percentage",
        "worker_fee_percentage",
        "tax_percentage",
    ):
        data[key] = float(data[key])
    data["amount_due_minor"] = max(data["total_minor"] - data["deposit_applied_minor"], 0)
    data["lines"] = [InvoiceLine.model_validate(dict(line)) for line in lines]
    return InvoiceResponse.model_validate(data)


async def load_owned_invoice(
    conn: asyncpg.Connection, invoice_id: UUID, scope: list[UUID]
) -> asyncpg.Record:
    row = await billing_repository.get_invoice(conn, invoice_id)
    if row is None or row["business_profile_id"] not in scope:
        raise not_found("invoice_not_found", MSG_INVOICE_NOT_FOUND)
    return row


async def _insert_invoice_with_lines(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    *,
    kind: str,
    charge: Charge,
    rates: FeeRates,
    status: str,
    now: datetime,
    worker_lines: list[tuple[UUID | None, str, int, int, int]],
    deposit_applied: int = 0,
    refund_due: int = 0,
    promo: Promo | None = None,
) -> UUID:
    """``worker_lines``: (assignment_id, description, minutes, rate, amount). Fee lines are
    net of the coupon; the discount is stored on the invoice."""
    net = as_business_charge(charge)
    invoice_id = await billing_repository.insert_invoice(
        conn,
        shift_id=shift["id"],
        business_profile_id=shift["business_profile_id"],
        reference=new_reference(INVOICE_REFERENCE_PREFIX),
        status=status,
        currency=shift["currency"],
        invoice_kind=kind,
        charge=net,
        fee_percentage=rates.business_pct,
        gateway_fee_percentage=rates.gateway_pct,
        worker_fee_percentage=rates.worker_pct,
        fee_policy_version=shift["fee_policy_version"],
        now=now,
        deposit_applied_minor=deposit_applied,
        refund_due_minor=refund_due,
        promo_discount_minor=charge.discount_minor,
        promo_code=promo.code if promo else None,
        tax_percentage=rates.tax_pct,
        tax_label=rates.tax_label if rates.tax_pct else None,
        tax_base=rates.tax_base if rates.tax_pct else None,
    )
    for index, (assignment_id, description, minutes, rate, amount) in enumerate(worker_lines):
        await billing_repository.insert_invoice_line(
            conn,
            invoice_id,
            assignment_id=assignment_id,
            line_kind=LINE_WORKER_PAY,
            description=description,
            minutes=minutes,
            rate_minor=rate,
            amount_minor=amount,
            sort_order=index,
        )
    fee_lines = [
        (LINE_PLATFORM_FEE, "Service fee", rates.business_pct, net.commission_minor),
        (LINE_GATEWAY_FEE, "Payment gateway charge", rates.gateway_pct, net.gateway_fee_minor),
    ]
    if rates.tax_pct:
        fee_lines.append((LINE_TAX, rates.tax_label, rates.tax_pct, net.tax_minor))
    for offset, (kind_, label, pct, amount) in enumerate(fee_lines):
        await billing_repository.insert_invoice_line(
            conn,
            invoice_id,
            assignment_id=None,
            line_kind=kind_,
            description=f"{label} ({pct.normalize()}%)",
            minutes=None,
            rate_minor=None,
            amount_minor=amount,
            sort_order=len(worker_lines) + offset,
        )
    return invoice_id


def worker_pay(
    assignment: asyncpg.Record, booked_minutes: int, shift: asyncpg.Record | None = None
) -> int:
    """Hourly: booked-window minutes at the rate; minutes past the booking (accepted
    extensions) at ``overtime_rate_pct``. Task: the fixed price unless the worker walked off
    (a task is paid for the result, not the time)."""
    if shift is not None and is_task(shift):
        if assignment["ended_reason"] == END_WORKER_LEFT:
            return 0
        return shift["task_price_minor"]
    minutes = assignment["approved_minutes"] or 0
    regular = min(minutes, booked_minutes)
    rate = assignment["hourly_rate_minor"]
    return pay_for_minutes(rate, regular) + overtime_pay(
        rate, minutes - regular, load_settings().overtime_rate_pct
    )


def _pay_line_label(
    assignment: asyncpg.Record, minutes: int, booked_minutes: int, *, task: bool = False
) -> str:
    name = assignment["full_name"] or "Worker"
    if task:
        done = assignment["ended_reason"] != END_WORKER_LEFT
        return f"{name} · task {'completed' if done else 'not completed'} (fixed price)"
    label = f"{name} · {minutes // 60}h {minutes % 60}m"
    overtime = max(minutes - booked_minutes, 0)
    if overtime:
        label += f" (incl. {overtime}m overtime @ {load_settings().overtime_rate_pct}%)"
    return label


async def create_deposit_invoice(
    conn: asyncpg.Connection, shift: asyncpg.Record, rates: FeeRates, now: datetime
) -> UUID:
    """Booked minutes × rate for every seat, paid before the shift goes live."""
    task = is_task(shift)
    minutes = (
        0 if task else paid_minutes(shift["starts_at"], shift["ends_at"], shift["break_minutes"])
    )
    pay = shift_seat_pay(shift)
    seats = shift["workers_required"]
    promo = await promo_service.shift_promo(conn, shift)
    return await _insert_invoice_with_lines(
        conn,
        shift,
        kind=INVOICE_KIND_DEPOSIT,
        charge=shift_charge(pay * seats, rates, promo),
        promo=promo,
        rates=rates,
        status=INVOICE_PENDING,
        now=now,
        worker_lines=[
            (
                None,
                f"{seats} × task (fixed price)"
                if task
                else f"{seats} × {minutes // 60}h {minutes % 60}m booked",
                minutes * seats,
                pay if task else shift["hourly_rate_minor"],
                pay * seats,
            )
        ],
    )


async def settle_cancelled_deposit(conn: asyncpg.Connection, shift_id: UUID) -> None:
    """Shift cancelled or expired before it ran: void an unpaid deposit, refund a paid one."""
    deposit = await billing_repository.get_invoice_by_shift(conn, shift_id, INVOICE_KIND_DEPOSIT)
    if deposit is None:
        return
    await promo_service.release_for_shift(conn, shift_id, utc_now())
    if deposit["status"] == INVOICE_PENDING:
        await billing_repository.cancel_pending_payments(conn, deposit["id"])
        await billing_repository.set_invoice_status(conn, deposit["id"], INVOICE_VOID)
    elif deposit["status"] == INVOICE_PAID:
        retained = await cancellation_repository.sum_retained(conn, shift_id)
        await billing_repository.set_refund_due(
            conn, deposit["id"], max(deposit["total_minor"] - retained, 0)
        )


async def generate_invoice(user: AuthenticatedUser, shift_id: UUID) -> InvoiceResponse:
    """Idempotent: returns the existing invoice if the shift was already invoiced."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            scope = await business_scope(conn, user.user_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            if shift is None or shift["business_profile_id"] not in scope:
                raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
            existing = await billing_repository.get_invoice_by_shift(conn, shift_id)
            if existing is not None:
                return await build_invoice_response(conn, existing["id"])
            if await live_work_repository.is_live_work(conn, shift_id):
                raise conflict(
                    "live_work_action_required",
                    "Live Work bills are issued automatically when the work is completed.",
                )
            if shift["status"] not in _INVOICEABLE_SHIFT_STATUSES:
                raise conflict("invoice_shift_state", MSG_INVOICE_SHIFT_STATE)
            unfinished = await assignment_repository.count_in(
                conn, shift_id, [*ASG_BOOKED_STATUSES, ASG_CHECKED_IN]
            )
            if unfinished:
                raise conflict(
                    "invoice_not_ready", MSG_INVOICE_NOT_READY, {"unfinished_workers": unfinished}
                )
            await attendance_repository.auto_approve_checked_out(
                conn, shift_id, now=now, approver_user_id=user.user_id
            )
            assignments = [
                a
                for a in await assignment_repository.list_shift_assignments(conn, shift_id)
                if a["status"] == ASG_APPROVED
            ]
            rates = catalog_service.shift_rates(shift) or await catalog_service.active_rates(conn)
            booked = paid_minutes(shift["starts_at"], shift["ends_at"], shift["break_minutes"])
            task = is_task(shift)
            pay_lines = [
                (a, a["approved_minutes"] or 0, worker_pay(a, booked, shift)) for a in assignments
            ]
            promo = await promo_service.shift_promo(conn, shift)
            charge = shift_charge(sum(amount for _, _, amount in pay_lines), rates, promo)
            await promo_service.mark_shift_applied(conn, shift_id, charge.discount_minor, now)
            deposit = await billing_repository.get_invoice_by_shift(
                conn, shift_id, INVOICE_KIND_DEPOSIT
            )
            deposit_paid = (
                max(
                    deposit["total_minor"]
                    - await cancellation_repository.sum_retained(conn, shift_id),
                    0,
                )
                if deposit and deposit["status"] == INVOICE_PAID
                else 0
            )
            refund_due = max(deposit_paid - charge.total_minor, 0)
            settled = charge.total_minor - deposit_paid <= 0
            invoice_id = await _insert_invoice_with_lines(
                conn,
                shift,
                kind=INVOICE_KIND_FINAL,
                charge=charge,
                promo=promo,
                rates=rates,
                status=INVOICE_PAID if settled else INVOICE_PENDING,
                now=now,
                worker_lines=[
                    (
                        a["id"],
                        _pay_line_label(a, minutes, booked, task=task),
                        minutes,
                        amount if task else a["hourly_rate_minor"],
                        amount,
                    )
                    for a, minutes, amount in pay_lines
                ],
                deposit_applied=deposit_paid,
                refund_due=refund_due,
            )
            if settled:
                await release_invoice_earnings(conn, invoice_id)
            if shift["status"] != SHIFT_COMPLETED:
                await shift_repository.set_status(
                    conn,
                    shift_id,
                    from_status=shift["status"],
                    to_status=SHIFT_COMPLETED,
                    now=now,
                    actor_user_id=user.user_id,
                    reason="invoiced",
                )
            return await build_invoice_response(conn, invoice_id)


async def get_shift_invoice(user: AuthenticatedUser, shift_id: UUID) -> InvoiceResponse:
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id)
        row = await billing_repository.get_invoice_by_shift(conn, shift_id)
        if row is None or row["business_profile_id"] not in scope:
            raise not_found("invoice_not_found", MSG_INVOICE_NOT_FOUND)
        return await build_invoice_response(conn, row["id"])


async def get_invoice(user: AuthenticatedUser, invoice_id: UUID) -> InvoiceResponse:
    async with get_pool().acquire() as conn:
        await load_owned_invoice(conn, invoice_id, await business_scope(conn, user.user_id))
        return await build_invoice_response(conn, invoice_id)
