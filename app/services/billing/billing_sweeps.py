"""Expire payment requests the business never completed."""

from __future__ import annotations

import asyncpg

from app.repositories.billing import billing_repository
from app.utils.clock import utc_now


async def expire_stale_payments(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await billing_repository.expire_due_payments(conn, utc_now())
