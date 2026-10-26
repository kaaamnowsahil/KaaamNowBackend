"""SQL for admin booking overrides and the per-booking ledger view."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

GET_BOOKING = """
SELECT a.id, a.status, a.shift_id, a.worker_profile_id, wp.user_id AS worker_user_id,
       u.full_name AS worker_name, s.job_title, s.currency, bp.business_name,
       bp.user_id AS business_user_id
FROM shift_assignments a
JOIN shifts s ON s.id = a.shift_id
JOIN business_profiles bp ON bp.id = s.business_profile_id
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
JOIN users u ON u.id = wp.user_id
WHERE a.id = $1
"""

LIST_INVOICES = """
SELECT invoice_kind || ' invoice (' || status || ')' AS description, total_minor,
       refund_due_minor, promo_discount_minor, issued_at
FROM shift_invoices WHERE shift_id = $1 ORDER BY issued_at DESC
"""

LIST_CHARGES = """
SELECT party, event, fee_minor, worker_compensation_minor, business_retained_minor,
       created_at
FROM cancellation_charges
WHERE assignment_id = $1 OR (shift_id = $2 AND assignment_id IS NULL)
ORDER BY created_at DESC
"""

LIST_WORKER_ENTRIES = """
SELECT entry_type, amount_minor, description, created_at
FROM earning_ledger_entries WHERE assignment_id = $1 ORDER BY created_at DESC
"""

LIST_STRIKES = """
SELECT weight, reason, voided_at, void_reason, created_at
FROM worker_strikes WHERE assignment_id = $1 ORDER BY created_at DESC
"""

LIST_VOUCHERS = """
SELECT p.code, p.is_active, p.used_count, p.valid_until, p.created_at
FROM cancellation_charges c JOIN promo_codes p ON p.id = c.voucher_promo_id
WHERE c.assignment_id = $1 OR (c.shift_id = $2 AND c.assignment_id IS NULL)
ORDER BY p.created_at DESC
"""

LIST_OVERRIDES = """
SELECT id, action, amount_minor, reason, admin_user_id, support_ticket_id, created_at
FROM admin_overrides WHERE assignment_id = $1 ORDER BY created_at DESC
"""

SUM_WAIVABLE = """
SELECT coalesce(-sum(amount_minor), 0)::bigint FROM earning_ledger_entries
WHERE assignment_id = $1 AND entry_type = ANY($2::text[])
"""

HAS_ENTRY = """
SELECT EXISTS (SELECT 1 FROM earning_ledger_entries WHERE assignment_id = $1 AND entry_type = $2)
"""

VOID_STRIKE = """
UPDATE worker_strikes SET voided_at = $2, voided_by_user_id = $3, void_reason = $4
WHERE assignment_id = $1 AND voided_at IS NULL
RETURNING worker_profile_id
"""

LIFT_RESTRICTIONS = """
UPDATE worker_profiles SET
    banned_at = CASE WHEN $2 THEN NULL ELSE banned_at END,
    feed_limited_until = CASE WHEN $3 THEN NULL ELSE feed_limited_until END,
    updated_at = now()
WHERE id = $1 AND (banned_at IS NOT NULL OR feed_limited_until IS NOT NULL)
RETURNING id
"""

DEACTIVATE_BOOKING_VOUCHER = """
UPDATE promo_codes p SET is_active = false, updated_at = now()
FROM cancellation_charges c
WHERE c.voucher_promo_id = p.id AND c.assignment_id = $1 AND p.is_active
RETURNING p.id
"""

LOCK_REFUNDABLE_INVOICE = """
SELECT * FROM shift_invoices
WHERE shift_id = $1 AND status = 'paid'
ORDER BY (invoice_kind = 'final') DESC
LIMIT 1
FOR UPDATE
"""

ADD_REFUND_DUE = """
UPDATE shift_invoices SET refund_due_minor = refund_due_minor + $2, updated_at = now()
WHERE id = $1
"""

INSERT_OVERRIDE = """
INSERT INTO admin_overrides (
    assignment_id, support_ticket_id, action, amount_minor, reason, admin_user_id
)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING id, action, amount_minor, reason, admin_user_id, support_ticket_id, created_at
"""


async def get_booking(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BOOKING, assignment_id)


async def ledger_rows(
    conn: asyncpg.Connection, assignment_id: UUID, shift_id: UUID
) -> dict[str, list[asyncpg.Record]]:
    return {
        "invoices": await conn.fetch(LIST_INVOICES, shift_id),
        "charges": await conn.fetch(LIST_CHARGES, assignment_id, shift_id),
        "worker_entries": await conn.fetch(LIST_WORKER_ENTRIES, assignment_id),
        "strikes": await conn.fetch(LIST_STRIKES, assignment_id),
        "vouchers": await conn.fetch(LIST_VOUCHERS, assignment_id, shift_id),
        "overrides": await conn.fetch(LIST_OVERRIDES, assignment_id),
    }


async def sum_waivable(
    conn: asyncpg.Connection, assignment_id: UUID, entry_types: tuple[str, ...]
) -> int:
    return await conn.fetchval(SUM_WAIVABLE, assignment_id, list(entry_types))


async def has_entry(conn: asyncpg.Connection, assignment_id: UUID, entry_type: str) -> bool:
    return await conn.fetchval(HAS_ENTRY, assignment_id, entry_type)


async def void_strike(
    conn: asyncpg.Connection, assignment_id: UUID, *, now: datetime, admin_id: UUID, reason: str
) -> UUID | None:
    return await conn.fetchval(VOID_STRIKE, assignment_id, now, admin_id, reason)


async def lift_restrictions(
    conn: asyncpg.Connection, worker_profile_id: UUID, *, unban: bool, unlimit: bool
) -> bool:
    return await conn.fetchval(LIFT_RESTRICTIONS, worker_profile_id, unban, unlimit) is not None


async def deactivate_booking_voucher(conn: asyncpg.Connection, assignment_id: UUID) -> bool:
    return await conn.fetchval(DEACTIVATE_BOOKING_VOUCHER, assignment_id) is not None


async def lock_refundable_invoice(
    conn: asyncpg.Connection, shift_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_REFUNDABLE_INVOICE, shift_id)


async def add_refund_due(conn: asyncpg.Connection, invoice_id: UUID, amount_minor: int) -> None:
    await conn.execute(ADD_REFUND_DUE, invoice_id, amount_minor)


async def insert_override(
    conn: asyncpg.Connection,
    *,
    assignment_id: UUID,
    support_ticket_id: UUID | None,
    action: str,
    amount_minor: int,
    reason: str,
    admin_user_id: UUID,
) -> asyncpg.Record:
    return await conn.fetchrow(
        INSERT_OVERRIDE,
        assignment_id,
        support_ticket_id,
        action,
        amount_minor,
        reason,
        admin_user_id,
    )
