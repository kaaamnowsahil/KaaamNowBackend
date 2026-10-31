"""asyncpg persistence for Live Work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.repositories.live_work import live_work_queries as q
from app.services.live_work.live_pricing import LiveCharge, LiveRates

# --- pricing settings ------------------------------------------------------------------


async def get_active_settings(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_ACTIVE_SETTINGS)


async def lock_settings(conn: asyncpg.Connection) -> None:
    """Serialise admin saves so two edits never both read the same "old" values."""
    await conn.execute("SELECT pg_advisory_xact_lock($1)", q.SETTINGS_LOCK_KEY)


async def insert_settings(
    conn: asyncpg.Connection,
    *,
    commission_pct: Decimal,
    tax_pct: Decimal,
    tax_label: str,
    tax_base: str,
    extension_surcharge_pct: Decimal,
    now: datetime,
    changed_by_user_id: UUID | None,
    changed_by_label: str,
    notes: str,
) -> asyncpg.Record:
    version = await conn.fetchval(q.NEXT_SETTINGS_VERSION)
    await conn.execute(q.DEACTIVATE_SETTINGS)
    return await conn.fetchrow(
        q.INSERT_SETTINGS,
        version,
        commission_pct,
        tax_pct,
        tax_label,
        tax_base,
        extension_surcharge_pct,
        now,
        changed_by_user_id,
        changed_by_label,
        notes,
    )


async def insert_audit(
    conn: asyncpg.Connection,
    *,
    settings_version: int,
    field: str,
    old_value: str | None,
    new_value: str,
    changed_by_user_id: UUID | None,
    changed_by_label: str,
    request_id: str | None,
    now: datetime,
) -> None:
    await conn.execute(
        q.INSERT_AUDIT,
        settings_version,
        field,
        old_value,
        new_value,
        changed_by_user_id,
        changed_by_label,
        request_id,
        now,
    )


async def list_audit(conn: asyncpg.Connection, limit: int, offset: int) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_AUDIT, limit, offset)


async def count_audit(conn: asyncpg.Connection) -> int:
    return int(await conn.fetchval(q.COUNT_AUDIT))


# --- bookings --------------------------------------------------------------------------


async def insert_booking_pricing(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    business_profile_id: UUID,
    currency: str,
    hourly_rate_minor: int,
    reserved_minutes: int,
    rates: LiveRates,
    charge: LiveCharge,
    idempotency_key: str | None,
    promo_code_id: UUID | None = None,
    promo_code: str | None = None,
    pricing_mode: str = "hourly",
    task_price_minor: int | None = None,
    workers_required: int = 1,
) -> None:
    await conn.execute(
        q.INSERT_BOOKING_PRICING,
        shift_id,
        business_profile_id,
        rates.version,
        currency,
        hourly_rate_minor,
        reserved_minutes,
        charge.base_amount_minor,
        rates.commission_pct,
        charge.commission_minor,
        rates.tax_pct,
        rates.tax_label,
        rates.tax_base,
        charge.taxable_minor,
        charge.tax_minor,
        charge.total_minor,
        charge.worker_commission_minor,
        charge.worker_net_minor,
        rates.extension_surcharge_pct,
        idempotency_key,
        promo_code_id,
        promo_code,
        charge.discount_minor,
        pricing_mode,
        task_price_minor,
        workers_required,
    )


async def get_booking_pricing(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_BOOKING_PRICING, shift_id)


async def find_booking_by_idempotency(
    conn: asyncpg.Connection, business_profile_id: UUID, key: str
) -> UUID | None:
    return await conn.fetchval(q.FIND_BOOKING_BY_IDEMPOTENCY, business_profile_id, key)


async def is_live_work(conn: asyncpg.Connection, shift_id: UUID) -> bool:
    return bool(await conn.fetchval(q.IS_LIVE_WORK, shift_id))


async def get_shift(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_SHIFT, shift_id)


async def set_awaiting_payment(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    now: datetime,
    fee_policy_version: int | None,
    commission_pct: Decimal,
) -> None:
    await conn.execute(q.SET_AWAITING_PAYMENT, shift_id, now, fee_policy_version, commission_pct)


async def start_search(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    starts_at: datetime,
    ends_at: datetime,
    radius_km: float,
    max_radius_km: float,
    expires_at: datetime,
) -> None:
    await conn.execute(
        q.START_SEARCH, shift_id, starts_at, ends_at, radius_km, max_radius_km, expires_at
    )


async def get_booking(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_BOOKING, shift_id)


async def list_business_bookings(
    conn: asyncpg.Connection, scope: list[UUID], *, active_only: bool, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_BUSINESS_BOOKINGS, scope, active_only, limit, offset)


async def get_current_assignment(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_CURRENT_ASSIGNMENT, shift_id)


async def list_assignments(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_ASSIGNMENTS, shift_id)


async def get_worker_active_assignment_id(
    conn: asyncpg.Connection, worker_profile_id: UUID
) -> UUID | None:
    return await conn.fetchval(q.GET_WORKER_ACTIVE_ASSIGNMENT, worker_profile_id)


async def list_worker_assignment_ids(
    conn: asyncpg.Connection, worker_profile_id: UUID, limit: int, offset: int
) -> list[UUID]:
    rows = await conn.fetch(q.LIST_WORKER_ASSIGNMENTS, worker_profile_id, limit, offset)
    return [r["id"] for r in rows]


async def set_assignment_started(conn: asyncpg.Connection, assignment_id: UUID) -> None:
    await conn.execute(q.SET_ASSIGNMENT_STARTED, assignment_id)


async def set_assignment_approved(conn: asyncpg.Connection, assignment_id: UUID) -> None:
    await conn.execute(q.SET_ASSIGNMENT_APPROVED, assignment_id)


async def set_shift_window(
    conn: asyncpg.Connection, shift_id: UUID, starts_at: datetime, ends_at: datetime
) -> None:
    await conn.execute(q.SET_SHIFT_WINDOW, shift_id, starts_at, ends_at)


async def extend_shift_end_to(conn: asyncpg.Connection, shift_id: UUID, ends_at: datetime) -> None:
    await conn.execute(q.EXTEND_SHIFT_END_TO, shift_id, ends_at)


async def set_shift_workers_required(conn: asyncpg.Connection, shift_id: UUID, seats: int) -> None:
    await conn.execute(q.SET_SHIFT_WORKERS_REQUIRED, shift_id, seats)


async def extend_shift_end(conn: asyncpg.Connection, shift_id: UUID, minutes: int) -> None:
    await conn.execute(q.EXTEND_SHIFT_END, shift_id, minutes)


async def list_open_offers_for_worker(
    conn: asyncpg.Connection, worker_profile_id: UUID, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_OPEN_OFFERS_FOR_WORKER, worker_profile_id, now)


async def get_dispatch(
    conn: asyncpg.Connection, shift_id: UUID, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_DISPATCH, shift_id, worker_profile_id)


@dataclass(frozen=True, slots=True)
class AvailableWorkersQuery:
    latitude: float
    longitude: float
    radius_km: float
    require_verified: bool
    fresh_since: datetime
    lat_delta: float
    lng_delta: float
    category_id: UUID | None
    business_user_id: UUID
    now: datetime

    def args(self) -> tuple[object, ...]:
        return (
            self.latitude,
            self.longitude,
            self.radius_km,
            self.require_verified,
            self.fresh_since,
            self.lat_delta,
            self.lng_delta,
            self.category_id,
            self.business_user_id,
            self.now,
        )


async def count_available_workers(conn: asyncpg.Connection, query: AvailableWorkersQuery) -> int:
    return int(await conn.fetchval(q.COUNT_AVAILABLE_WORKERS, *query.args()))


async def list_available_worker_points(
    conn: asyncpg.Connection, query: AvailableWorkersQuery, limit: int
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_AVAILABLE_WORKER_POINTS, *query.args(), limit)


# --- arrival codes ---------------------------------------------------------------------


async def insert_arrival_code(
    conn: asyncpg.Connection,
    *,
    assignment_id: UUID,
    shift_id: UUID,
    code: str,
    expires_at: datetime,
) -> None:
    await conn.execute(q.INSERT_ARRIVAL_CODE, assignment_id, shift_id, code, expires_at)


async def get_arrival_code(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_ARRIVAL_CODE, assignment_id)


async def lock_arrival_code(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.LOCK_ARRIVAL_CODE, assignment_id)


async def record_failed_attempt(
    conn: asyncpg.Connection, assignment_id: UUID, *, max_attempts: int, now: datetime
) -> asyncpg.Record | None:
    return await conn.fetchrow(q.RECORD_FAILED_ATTEMPT, assignment_id, max_attempts, now)


async def set_arrival_verified(
    conn: asyncpg.Connection, assignment_id: UUID, now: datetime
) -> None:
    await conn.execute(q.SET_ARRIVAL_VERIFIED, assignment_id, now)


async def reissue_arrival_code(
    conn: asyncpg.Connection, assignment_id: UUID, *, code: str, expires_at: datetime
) -> None:
    await conn.execute(q.REISSUE_ARRIVAL_CODE, assignment_id, code, expires_at)


# --- extensions ------------------------------------------------------------------------


async def insert_extension(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    assignment_id: UUID,
    extra_minutes: int,
    hourly_rate_minor: int,
    surcharge_pct: Decimal,
    extension_rate_minor: int,
    commission_pct: Decimal,
    tax_pct: Decimal,
    tax_base: str,
    charge: LiveCharge,
    requested_by_user_id: UUID,
    now: datetime,
) -> UUID:
    return await conn.fetchval(
        q.INSERT_EXTENSION,
        shift_id,
        assignment_id,
        extra_minutes,
        hourly_rate_minor,
        surcharge_pct,
        extension_rate_minor,
        charge.base_amount_minor,
        commission_pct,
        charge.commission_minor,
        tax_pct,
        tax_base,
        charge.tax_minor,
        charge.total_minor,
        charge.worker_commission_minor,
        charge.worker_net_minor,
        requested_by_user_id,
        now,
    )


async def get_extension(conn: asyncpg.Connection, extension_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_EXTENSION, extension_id)


async def lock_extension(conn: asyncpg.Connection, extension_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.LOCK_EXTENSION, extension_id)


async def lock_extension_by_invoice(
    conn: asyncpg.Connection, invoice_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(q.LOCK_EXTENSION_BY_INVOICE, invoice_id)


async def list_extensions(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_EXTENSIONS, shift_id)


async def set_extension_status(
    conn: asyncpg.Connection, extension_id: UUID, status: str, now: datetime
) -> None:
    await conn.execute(q.SET_EXTENSION_STATUS, extension_id, status, now)


async def set_extension_invoice(
    conn: asyncpg.Connection, extension_id: UUID, invoice_id: UUID
) -> None:
    await conn.execute(q.SET_EXTENSION_INVOICE, extension_id, invoice_id)


async def list_due_extensions(
    conn: asyncpg.Connection, requested_before: datetime, accepted_before: datetime
) -> list[UUID]:
    rows = await conn.fetch(q.LIST_DUE_EXTENSIONS, requested_before, accepted_before)
    return [r["id"] for r in rows]


# --- invoices / payments ---------------------------------------------------------------


async def insert_live_invoice(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    business_profile_id: UUID,
    reference: str,
    status: str,
    currency: str,
    kind: str,
    worker_subtotal_minor: int,
    commission_minor: int,
    tax_minor: int,
    commission_pct: Decimal,
    tax_pct: Decimal,
    tax_label: str,
    tax_base: str,
    fee_policy_version: int,
    live_pricing_version: int,
    now: datetime,
    deposit_applied_minor: int = 0,
    refund_due_minor: int = 0,
    promo_code: str | None = None,
    promo_discount_minor: int = 0,
    assignment_id: UUID | None = None,
) -> UUID:
    """``commission_minor`` is what the Business pays, i.e. already net of any coupon.
    ``assignment_id``: set on a Worker's final bill only."""
    total = worker_subtotal_minor + commission_minor + tax_minor
    return await conn.fetchval(
        q.INSERT_LIVE_INVOICE,
        shift_id,
        business_profile_id,
        reference,
        status,
        currency,
        worker_subtotal_minor,
        commission_minor,
        total,
        commission_pct,
        fee_policy_version,
        now,
        now if status == "paid" else None,
        kind,
        deposit_applied_minor,
        refund_due_minor,
        tax_minor,
        tax_pct,
        tax_label,
        tax_base,
        live_pricing_version,
        promo_code,
        promo_discount_minor,
        assignment_id,
    )


async def list_shift_invoices(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_SHIFT_INVOICES, shift_id)


async def get_succeeded_payment(
    conn: asyncpg.Connection, invoice_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_SUCCEEDED_PAYMENT, invoice_id)


async def add_refund_due(conn: asyncpg.Connection, invoice_id: UUID, amount_minor: int) -> None:
    await conn.execute(q.ADD_REFUND_DUE, invoice_id, amount_minor)


# --- refunds ---------------------------------------------------------------------------


async def insert_refund(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    payment: asyncpg.Record,
    amount_minor: int,
    reason: str,
    idempotency_key: str,
    created_by_user_id: UUID | None,
    assignment_id: UUID | None = None,
) -> UUID | None:
    return await conn.fetchval(
        q.INSERT_REFUND,
        shift_id,
        payment["id"],
        payment["invoice_id"],
        amount_minor,
        payment["currency"],
        reason,
        idempotency_key,
        payment["provider"],
        created_by_user_id,
        assignment_id,
    )


async def refund_amount(conn: asyncpg.Connection, refund_id: UUID) -> int:
    return int(await conn.fetchval(q.REFUND_AMOUNT, refund_id))


async def payment_refunded_minor(conn: asyncpg.Connection, payment_id: UUID) -> int:
    return int(await conn.fetchval(q.SUM_PAYMENT_REFUNDS, payment_id))


async def list_refunds(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_REFUNDS, shift_id)


async def lock_due_refunds(
    conn: asyncpg.Connection, max_attempts: int, limit: int
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LOCK_DUE_REFUNDS, max_attempts, limit)


async def lock_refund(conn: asyncpg.Connection, refund_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.LOCK_REFUND, refund_id)


async def set_refund_result(
    conn: asyncpg.Connection,
    refund_id: UUID,
    *,
    status: str,
    provider_refund_id: str | None,
    failure_reason: str | None,
    now: datetime,
) -> None:
    await conn.execute(
        q.SET_REFUND_RESULT, refund_id, status, provider_refund_id, failure_reason, now
    )


async def reset_refund_attempts(conn: asyncpg.Connection, refund_id: UUID) -> None:
    await conn.execute(q.RESET_REFUND_ATTEMPTS, refund_id)


# --- sweeps ----------------------------------------------------------------------------


async def list_unpaid_bookings(conn: asyncpg.Connection, posted_before: datetime) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(q.LIST_UNPAID_BOOKINGS, posted_before)]


async def list_overdue_active_seats(
    conn: asyncpg.Connection, ended_before: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_OVERDUE_ACTIVE_SEATS, ended_before)


# --- admin -----------------------------------------------------------------------------


async def admin_list_bookings(
    conn: asyncpg.Connection, status: str | None, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(q.ADMIN_LIST_BOOKINGS, status, limit, offset)


async def admin_count_bookings(conn: asyncpg.Connection, status: str | None) -> int:
    return int(await conn.fetchval(q.ADMIN_COUNT_BOOKINGS, status))


async def admin_list_cancellations(
    conn: asyncpg.Connection, shift_id: UUID
) -> list[asyncpg.Record]:
    return await conn.fetch(q.ADMIN_LIST_CANCELLATIONS, shift_id)


async def admin_get_booking(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.ADMIN_GET_BOOKING, shift_id)


async def admin_list_refunds(
    conn: asyncpg.Connection, status: str | None, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(q.ADMIN_LIST_REFUNDS, status, limit, offset)


async def admin_count_refunds(conn: asyncpg.Connection, status: str | None) -> int:
    return int(await conn.fetchval(q.ADMIN_COUNT_REFUNDS, status))


async def admin_list_shift_refunds(
    conn: asyncpg.Connection, shift_id: UUID
) -> list[asyncpg.Record]:
    return await conn.fetch(q.ADMIN_LIST_SHIFT_REFUNDS, shift_id)


async def admin_get_refund(conn: asyncpg.Connection, refund_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.ADMIN_GET_REFUND, refund_id)
