"""SQL for promo_codes and promo_redemptions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

_PROMO_COLUMNS = """
id, code, target_role, discount_type, discount_value, applies_to, max_discount_minor,
valid_from, valid_until, max_uses, max_uses_per_user, used_count, owner_user_id, source,
is_active, booking_types, min_booking_minor, is_listed, title
"""

LOCK_BY_CODE = f"SELECT {_PROMO_COLUMNS} FROM promo_codes WHERE upper(code) = upper($1) FOR UPDATE"
GET_BY_CODE = f"SELECT {_PROMO_COLUMNS} FROM promo_codes WHERE upper(code) = upper($1)"
GET_BY_ID = f"SELECT {_PROMO_COLUMNS} FROM promo_codes WHERE id = $1"

COUNT_USER_USES = """
SELECT count(*) FROM promo_redemptions
WHERE promo_code_id = $1 AND user_id = $2 AND status <> 'released'
"""

INSERT_REDEMPTION = """
INSERT INTO promo_redemptions (promo_code_id, user_id, shift_id)
VALUES ($1, $2, $3)
RETURNING id
"""

INCREMENT_USED = """
UPDATE promo_codes SET used_count = used_count + $2, updated_at = now() WHERE id = $1
"""

LOCK_SHIFT_REDEMPTION = """
SELECT * FROM promo_redemptions WHERE shift_id = $1 AND status <> 'released' FOR UPDATE
"""

LOCK_WORKER_PENDING = """
SELECT r.*, p.code FROM promo_redemptions r JOIN promo_codes p ON p.id = r.promo_code_id
WHERE r.user_id = $1 AND r.shift_id IS NULL AND r.status = 'reserved'
FOR UPDATE OF r
"""

APPLY_REDEMPTION = """
UPDATE promo_redemptions SET status = 'applied', discount_minor = $2, assignment_id = $3,
    applied_at = $4
WHERE id = $1
"""

RELEASE_REDEMPTION = """
UPDATE promo_redemptions SET status = 'released', released_at = $2 WHERE id = $1
"""

LIST_OWNED_VOUCHERS = f"""
SELECT {_PROMO_COLUMNS} FROM promo_codes
WHERE owner_user_id = $1 AND is_active AND used_count < coalesce(max_uses, 2147483647)
  AND (valid_until IS NULL OR valid_until > $2)
ORDER BY valid_until NULLS LAST
"""

LIST_BUSINESS_OFFERS = f"""
SELECT {_PROMO_COLUMNS} FROM promo_codes
WHERE target_role = 'business' AND is_active
  AND (owner_user_id = $1 OR (owner_user_id IS NULL AND is_listed))
  AND (valid_until IS NULL OR valid_until > $2)
ORDER BY owner_user_id IS NULL, valid_until NULLS LAST, code
LIMIT 50
"""

COUNT_USER_USES_MANY = """
SELECT promo_code_id, count(*) AS uses FROM promo_redemptions
WHERE user_id = $1 AND promo_code_id = ANY($2::uuid[]) AND status <> 'released'
GROUP BY promo_code_id
"""

RESTORE_REDEMPTION = """
UPDATE promo_redemptions SET status = 'released', released_at = $2
WHERE id = $1 AND status <> 'released'
"""

SET_SHIFT_PROMO = "UPDATE shifts SET promo_code_id = $2, updated_at = now() WHERE id = $1"


async def lock_by_code(conn: asyncpg.Connection, code: str) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_BY_CODE, code.strip())


async def get_by_code(conn: asyncpg.Connection, code: str) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BY_CODE, code.strip())


async def get_by_id(conn: asyncpg.Connection, promo_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BY_ID, promo_id)


async def count_user_uses(conn: asyncpg.Connection, promo_id: UUID, user_id: UUID) -> int:
    return await conn.fetchval(COUNT_USER_USES, promo_id, user_id)


async def reserve(
    conn: asyncpg.Connection, promo_id: UUID, user_id: UUID, shift_id: UUID | None
) -> UUID:
    redemption_id = await conn.fetchval(INSERT_REDEMPTION, promo_id, user_id, shift_id)
    await conn.execute(INCREMENT_USED, promo_id, 1)
    return redemption_id


async def lock_shift_redemption(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_SHIFT_REDEMPTION, shift_id)


async def lock_worker_pending(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_WORKER_PENDING, user_id)


async def apply(
    conn: asyncpg.Connection,
    redemption_id: UUID,
    *,
    discount_minor: int,
    assignment_id: UUID | None,
    now: datetime,
) -> None:
    await conn.execute(APPLY_REDEMPTION, redemption_id, discount_minor, assignment_id, now)


async def release(conn: asyncpg.Connection, redemption: asyncpg.Record, now: datetime) -> None:
    await conn.execute(RELEASE_REDEMPTION, redemption["id"], now)
    await conn.execute(INCREMENT_USED, redemption["promo_code_id"], -1)


async def list_owned_vouchers(
    conn: asyncpg.Connection, user_id: UUID, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_OWNED_VOUCHERS, user_id, now)


async def list_business_offers(
    conn: asyncpg.Connection, user_id: UUID, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_BUSINESS_OFFERS, user_id, now)


async def count_user_uses_many(
    conn: asyncpg.Connection, user_id: UUID, promo_ids: list[UUID]
) -> dict[UUID, int]:
    rows = await conn.fetch(COUNT_USER_USES_MANY, user_id, promo_ids)
    return {r["promo_code_id"]: r["uses"] for r in rows}


async def restore(conn: asyncpg.Connection, redemption: asyncpg.Record, now: datetime) -> None:
    """Give a reserved or applied use back (booking ended with everything refunded)."""
    if await conn.execute(RESTORE_REDEMPTION, redemption["id"], now) == "UPDATE 1":
        await conn.execute(INCREMENT_USED, redemption["promo_code_id"], -1)


async def attach_to_shift(conn: asyncpg.Connection, shift_id: UUID, promo_id: UUID) -> None:
    await conn.execute(SET_SHIFT_PROMO, shift_id, promo_id)
