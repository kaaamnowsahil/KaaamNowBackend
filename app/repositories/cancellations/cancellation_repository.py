"""asyncpg persistence for cancellation policies, charges, strikes and system vouchers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import asyncpg

GET_ACTIVE_POLICY = """
SELECT version, strike_window_days, strikes_to_limit, limit_days, strikes_to_ban,
       voucher_valid_days
FROM cancellation_policies WHERE is_active
"""

LIST_POLICY_TIERS = """
SELECT party, event, hours_from, hours_to, flat_fee_minor, booking_pct, fee_cap_minor,
       worker_share_pct, strike_weight, business_voucher
FROM cancellation_policy_tiers WHERE policy_version = $1
ORDER BY party, event, hours_from DESC
"""

INSERT_CHARGE = """
INSERT INTO cancellation_charges (
    shift_id, assignment_id, party, event, policy_version, hours_before, seats, booking_minor,
    fee_minor, worker_compensation_minor, business_refund_minor, business_retained_minor,
    strike_weight, voucher_promo_id, currency, created_by_user_id
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
RETURNING id
"""

SUM_RETAINED = """
SELECT COALESCE(SUM(business_retained_minor), 0) FROM cancellation_charges WHERE shift_id = $1
"""

INSERT_WORKER_LEDGER = """
INSERT INTO earning_ledger_entries (
    worker_profile_id, entry_type, amount_minor, currency, assignment_id, description
)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT DO NOTHING
"""

INSERT_STRIKE = """
INSERT INTO worker_strikes (worker_profile_id, assignment_id, weight, reason, expires_at)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT DO NOTHING
"""

ACTIVE_STRIKE_WEIGHT = """
SELECT COALESCE(SUM(weight), 0) FROM worker_strikes
WHERE worker_profile_id = $1 AND voided_at IS NULL AND expires_at > $2
"""

LIMIT_WORKER_FEED = """
UPDATE worker_profiles SET feed_limited_until = GREATEST(COALESCE(feed_limited_until, $2), $2),
    updated_at = now()
WHERE id = $1
"""

BAN_WORKER = """
UPDATE worker_profiles SET banned_at = $2, updated_at = now()
WHERE id = $1 AND banned_at IS NULL
RETURNING id
"""

INSERT_VOUCHER = """
INSERT INTO promo_codes (
    code, target_role, discount_type, applies_to, valid_until, max_uses, max_uses_per_user,
    owner_user_id, source, source_shift_id
)
VALUES ($1, 'business', 'waive_fees', 'all_fees', $2, 1, 1, $3, 'system', $4)
RETURNING id
"""


async def get_active_policy(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_ACTIVE_POLICY)


async def list_policy_tiers(conn: asyncpg.Connection, version: int) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_POLICY_TIERS, version)


async def insert_charge(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    assignment_id: UUID | None,
    party: str,
    event: str,
    policy_version: int | None,
    hours_before: Decimal,
    seats: int,
    booking_minor: int,
    fee_minor: int,
    worker_compensation_minor: int,
    business_refund_minor: int,
    business_retained_minor: int,
    strike_weight: Decimal,
    voucher_promo_id: UUID | None,
    currency: str,
    actor_user_id: UUID | None,
) -> UUID:
    return await conn.fetchval(
        INSERT_CHARGE,
        shift_id,
        assignment_id,
        party,
        event,
        policy_version,
        hours_before,
        seats,
        booking_minor,
        fee_minor,
        worker_compensation_minor,
        business_refund_minor,
        business_retained_minor,
        strike_weight,
        voucher_promo_id,
        currency,
        actor_user_id,
    )


async def sum_retained(conn: asyncpg.Connection, shift_id: UUID) -> int:
    return await conn.fetchval(SUM_RETAINED, shift_id)


async def insert_worker_ledger(
    conn: asyncpg.Connection,
    *,
    worker_profile_id: UUID,
    entry_type: str,
    amount_minor: int,
    currency: str,
    assignment_id: UUID,
    description: str,
) -> None:
    await conn.execute(
        INSERT_WORKER_LEDGER,
        worker_profile_id,
        entry_type,
        amount_minor,
        currency,
        assignment_id,
        description,
    )


async def insert_strike(
    conn: asyncpg.Connection,
    *,
    worker_profile_id: UUID,
    assignment_id: UUID | None,
    weight: Decimal,
    reason: str,
    expires_at: datetime,
) -> None:
    await conn.execute(INSERT_STRIKE, worker_profile_id, assignment_id, weight, reason, expires_at)


async def active_strike_weight(
    conn: asyncpg.Connection, worker_profile_id: UUID, now: datetime
) -> Decimal:
    return await conn.fetchval(ACTIVE_STRIKE_WEIGHT, worker_profile_id, now)


async def limit_worker_feed(
    conn: asyncpg.Connection, worker_profile_id: UUID, until: datetime
) -> None:
    await conn.execute(LIMIT_WORKER_FEED, worker_profile_id, until)


async def ban_worker(conn: asyncpg.Connection, worker_profile_id: UUID, now: datetime) -> bool:
    return await conn.fetchval(BAN_WORKER, worker_profile_id, now) is not None


async def insert_voucher(
    conn: asyncpg.Connection,
    *,
    code: str,
    owner_user_id: UUID,
    source_shift_id: UUID,
    valid_until: datetime,
) -> UUID:
    return await conn.fetchval(INSERT_VOUCHER, code, valid_until, owner_user_id, source_shift_id)
