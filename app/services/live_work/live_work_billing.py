"""Live Work invoices. Every amount comes from the booking's price snapshot.

* deposit        — reserved amount (base + commission − coupon + tax), paid before Workers are
                   notified.
* live_extension — one per approved extension, paid before the time is added.
* final          — issued on completion: one worker-pay line (reserved + applied extensions, the
                   task price, or worked time on a walk-off — nothing for an unfinished task) so
                   worker earnings are credited exactly once.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.constants.billing.billing_route_strings import (
    INVOICE_KIND_DEPOSIT,
    INVOICE_KIND_FINAL,
    INVOICE_PAID,
    INVOICE_PENDING,
    INVOICE_VOID,
    LINE_PLATFORM_FEE,
    LINE_TAX,
    LINE_WORKER_PAY,
)
from app.constants.shifts.shift_route_strings import PRICING_TASK
from app.repositories.billing import billing_repository
from app.repositories.live_work import live_work_repository
from app.services.billing.settlement import release_invoice_earnings
from app.services.live_work.live_pricing import LiveCharge, taxable_amount
from app.services.live_work.live_pricing_settings_service import tax_base_description
from app.utils.references import INVOICE_REFERENCE_PREFIX, new_reference

INVOICE_KIND_LIVE_EXTENSION = "live_extension"


def _rupees(minor: int) -> str:
    return f"₹{minor // 100:,}.{minor % 100:02d}"


def _duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _is_task(pricing: asyncpg.Record) -> bool:
    return pricing["pricing_mode"] == PRICING_TASK


def _pct(value: Decimal) -> str:
    return f"{Decimal(value).normalize():f}"


def _commission_line(pricing: asyncpg.Record, charge: LiveCharge) -> str:
    text = f"Platform commission {_pct(pricing['commission_pct'])}%"
    if charge.discount_minor:
        text += (
            f" {_rupees(charge.commission_minor)} − coupon {pricing['promo_code']} "
            f"{_rupees(charge.discount_minor)}"
        )
    return text[:200]


async def _insert(
    conn: asyncpg.Connection,
    pricing: asyncpg.Record,
    *,
    kind: str,
    status: str,
    charge: LiveCharge,
    worker_line: tuple[UUID | None, str, int | None, int | None],
    now: datetime,
    deposit_applied: int = 0,
    refund_due: int = 0,
) -> UUID:
    """``worker_line``: (assignment_id, description, minutes, rate)."""
    invoice_id = await live_work_repository.insert_live_invoice(
        conn,
        shift_id=pricing["shift_id"],
        business_profile_id=pricing["business_profile_id"],
        reference=new_reference(INVOICE_REFERENCE_PREFIX),
        status=status,
        currency=pricing["currency"],
        kind=kind,
        worker_subtotal_minor=charge.base_amount_minor,
        commission_minor=charge.net_commission_minor,
        tax_minor=charge.tax_minor,
        commission_pct=pricing["commission_pct"],
        tax_pct=pricing["tax_pct"],
        tax_label=pricing["tax_label"],
        tax_base=pricing["tax_base"],
        fee_policy_version=pricing["settings_version"],
        live_pricing_version=pricing["settings_version"],
        now=now,
        deposit_applied_minor=deposit_applied,
        refund_due_minor=refund_due,
        promo_code=pricing["promo_code"] if charge.discount_minor else None,
        promo_discount_minor=charge.discount_minor,
    )
    assignment_id, description, minutes, rate = worker_line
    await billing_repository.insert_invoice_line(
        conn,
        invoice_id,
        assignment_id=assignment_id,
        line_kind=LINE_WORKER_PAY,
        description=description,
        minutes=minutes,
        rate_minor=rate,
        amount_minor=charge.base_amount_minor,
        sort_order=0,
    )
    await billing_repository.insert_invoice_line(
        conn,
        invoice_id,
        assignment_id=None,
        line_kind=LINE_PLATFORM_FEE,
        description=_commission_line(pricing, charge),
        minutes=None,
        rate_minor=None,
        amount_minor=charge.net_commission_minor,
        sort_order=1,
    )
    await billing_repository.insert_invoice_line(
        conn,
        invoice_id,
        assignment_id=None,
        line_kind=LINE_TAX,
        description=(
            f"{pricing['tax_label']} {_pct(pricing['tax_pct'])}% on "
            f"{_rupees(charge.taxable_minor)} — "
            f"{tax_base_description(pricing['tax_base'], pricing['tax_label'])}"
        )[:200],
        minutes=None,
        rate_minor=None,
        amount_minor=charge.tax_minor,
        sort_order=2,
    )
    return invoice_id


def snapshot_charge(pricing: asyncpg.Record) -> LiveCharge:
    return LiveCharge(
        base_amount_minor=pricing["base_amount_minor"],
        commission_minor=pricing["commission_minor"],
        taxable_minor=pricing["taxable_minor"],
        tax_minor=pricing["tax_minor"],
        worker_commission_minor=pricing["worker_commission_minor"],
        discount_minor=pricing["promo_discount_minor"],
    )


def extension_snapshot_charge(extension: asyncpg.Record) -> LiveCharge:
    return LiveCharge(
        base_amount_minor=extension["base_amount_minor"],
        commission_minor=extension["commission_minor"],
        taxable_minor=taxable_amount(
            extension["base_amount_minor"], extension["commission_minor"], extension["tax_base"]
        ),
        tax_minor=extension["tax_minor"],
        worker_commission_minor=extension["worker_commission_minor"],
    )


async def create_deposit_invoice(
    conn: asyncpg.Connection, pricing: asyncpg.Record, now: datetime
) -> UUID:
    return await _insert(
        conn,
        pricing,
        kind=INVOICE_KIND_DEPOSIT,
        status=INVOICE_PENDING,
        charge=snapshot_charge(pricing),
        worker_line=(
            (None, "Task (fixed price)", None, pricing["task_price_minor"])
            if _is_task(pricing)
            else (
                None,
                f"Reserved {_duration(pricing['reserved_minutes'])} × "
                f"{_rupees(pricing['hourly_rate_minor'])}/h",
                pricing["reserved_minutes"],
                pricing["hourly_rate_minor"],
            )
        ),
        now=now,
    )


async def create_extension_invoice(
    conn: asyncpg.Connection, pricing: asyncpg.Record, extension: asyncpg.Record, now: datetime
) -> UUID:
    charge = extension_snapshot_charge(extension)
    return await _insert(
        conn,
        pricing,
        kind=INVOICE_KIND_LIVE_EXTENSION,
        status=INVOICE_PENDING,
        charge=charge,
        worker_line=(
            None,
            f"Extension {_duration(extension['extra_minutes'])} × "
            f"{_rupees(extension['extension_rate_minor'])}/h "
            f"(base {_rupees(extension['hourly_rate_minor'])}/h + "
            f"{_pct(extension['surcharge_pct'])}%)",
            extension["extra_minutes"],
            extension["extension_rate_minor"],
        ),
        now=now,
    )


async def void_invoice(conn: asyncpg.Connection, invoice_id: UUID) -> None:
    invoice = await billing_repository.lock_invoice(conn, invoice_id)
    if invoice is None or invoice["status"] != INVOICE_PENDING:
        return
    await billing_repository.cancel_pending_payments(conn, invoice_id)
    await billing_repository.set_invoice_status(conn, invoice_id, INVOICE_VOID)


async def paid_invoices(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    """Deposit + extension invoices that were paid (newest first, for refund ordering)."""
    rows = await live_work_repository.list_shift_invoices(conn, shift_id)
    paid = [
        r
        for r in rows
        if r["status"] == INVOICE_PAID
        and r["invoice_kind"] in (INVOICE_KIND_DEPOSIT, INVOICE_KIND_LIVE_EXTENSION)
    ]
    return list(reversed(paid))


async def create_final_invoice(
    conn: asyncpg.Connection,
    pricing: asyncpg.Record,
    *,
    assignment_id: UUID,
    charge: LiveCharge,
    description: str,
    minutes: int,
    paid_minor: int,
    now: datetime,
) -> UUID:
    """Final bill against what was already paid. Releases worker earnings when covered."""
    refund_due = max(paid_minor - charge.total_minor, 0)
    settled = charge.total_minor <= paid_minor
    invoice_id = await _insert(
        conn,
        pricing,
        kind=INVOICE_KIND_FINAL,
        status=INVOICE_PAID if settled else INVOICE_PENDING,
        charge=charge,
        worker_line=(
            assignment_id,
            description,
            minutes,
            pricing["task_price_minor"] if _is_task(pricing) else pricing["hourly_rate_minor"],
        ),
        now=now,
        deposit_applied=paid_minor,
        refund_due=refund_due,
    )
    if settled:
        await release_invoice_earnings(conn, invoice_id)
    return invoice_id
