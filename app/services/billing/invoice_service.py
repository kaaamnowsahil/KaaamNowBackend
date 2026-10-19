"""Final cost: approved minutes × rate per worker + platform fee (snapshotted at publish)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg

from app.constants.billing.billing_route_strings import (
    INVOICE_PAID,
    INVOICE_PENDING,
    LINE_PLATFORM_FEE,
    LINE_WORKER_PAY,
    MSG_INVOICE_NOT_FOUND,
    MSG_INVOICE_NOT_READY,
    MSG_INVOICE_SHIFT_STATE,
)
from app.constants.shifts.shift_route_strings import (
    ASG_APPROVED,
    ASG_BOOKED_STATUSES,
    ASG_CHECKED_IN,
    MSG_SHIFT_NOT_FOUND,
    SHIFT_COMPLETED,
    SHIFT_FILLED,
    SHIFT_IN_PROGRESS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.repositories.attendance import attendance_repository
from app.repositories.billing import billing_repository
from app.repositories.shifts import assignment_repository, shift_repository
from app.schemas.billing.billing_schemas import InvoiceLine, InvoiceResponse
from app.security.authenticated_user import AuthenticatedUser
from app.services.profiles.profile_lookup import require_business_profile
from app.utils.clock import utc_now
from app.utils.money import pay_for_minutes, platform_fee
from app.utils.references import INVOICE_REFERENCE_PREFIX, new_reference

_INVOICEABLE_SHIFT_STATUSES = (SHIFT_FILLED, SHIFT_IN_PROGRESS, SHIFT_COMPLETED)


async def build_invoice_response(conn: asyncpg.Connection, invoice_id: UUID) -> InvoiceResponse:
    row = await billing_repository.get_invoice(conn, invoice_id)
    lines = await billing_repository.list_invoice_lines(conn, invoice_id)
    data = dict(row)
    data["fee_percentage"] = float(data["fee_percentage"])
    data["lines"] = [InvoiceLine.model_validate(dict(line)) for line in lines]
    return InvoiceResponse.model_validate(data)


async def load_owned_invoice(
    conn: asyncpg.Connection, invoice_id: UUID, business_profile_id: UUID
) -> asyncpg.Record:
    row = await billing_repository.get_invoice(conn, invoice_id)
    if row is None or row["business_profile_id"] != business_profile_id:
        raise not_found("invoice_not_found", MSG_INVOICE_NOT_FOUND)
    return row


async def generate_invoice(user: AuthenticatedUser, shift_id: UUID) -> InvoiceResponse:
    """Idempotent: returns the existing invoice if the shift was already invoiced."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_business_profile(conn, user.user_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            if shift is None or shift["business_profile_id"] != business["id"]:
                raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
            existing = await billing_repository.get_invoice_by_shift(conn, shift_id)
            if existing is not None:
                return await build_invoice_response(conn, existing["id"])
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
            pct = Decimal(shift["fee_percentage"])
            pay_lines = [
                (
                    a,
                    a["approved_minutes"] or 0,
                    pay_for_minutes(a["hourly_rate_minor"], a["approved_minutes"] or 0),
                )
                for a in assignments
            ]
            subtotal = sum(amount for _, _, amount in pay_lines)
            fee = platform_fee(subtotal, pct)
            invoice_id = await billing_repository.insert_invoice(
                conn,
                shift_id=shift_id,
                business_profile_id=business["id"],
                reference=new_reference(INVOICE_REFERENCE_PREFIX),
                status=INVOICE_PENDING if subtotal + fee > 0 else INVOICE_PAID,
                currency=shift["currency"],
                worker_subtotal_minor=subtotal,
                platform_fee_minor=fee,
                fee_percentage=pct,
                fee_policy_version=shift["fee_policy_version"],
                now=now,
            )
            for index, (a, minutes, amount) in enumerate(pay_lines):
                await billing_repository.insert_invoice_line(
                    conn,
                    invoice_id,
                    assignment_id=a["id"],
                    line_kind=LINE_WORKER_PAY,
                    description=f"{a['full_name'] or 'Worker'} · {minutes // 60}h {minutes % 60}m",
                    minutes=minutes,
                    rate_minor=a["hourly_rate_minor"],
                    amount_minor=amount,
                    sort_order=index,
                )
            await billing_repository.insert_invoice_line(
                conn,
                invoice_id,
                assignment_id=None,
                line_kind=LINE_PLATFORM_FEE,
                description=f"Platform fee ({pct.normalize()}%)",
                minutes=None,
                rate_minor=None,
                amount_minor=fee,
                sort_order=len(pay_lines),
            )
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
        business = await require_business_profile(conn, user.user_id)
        row = await billing_repository.get_invoice_by_shift(conn, shift_id)
        if row is None or row["business_profile_id"] != business["id"]:
            raise not_found("invoice_not_found", MSG_INVOICE_NOT_FOUND)
        return await build_invoice_response(conn, row["id"])


async def get_invoice(user: AuthenticatedUser, invoice_id: UUID) -> InvoiceResponse:
    async with get_pool().acquire() as conn:
        business = await require_business_profile(conn, user.user_id)
        await load_owned_invoice(conn, invoice_id, business["id"])
        return await build_invoice_response(conn, invoice_id)
