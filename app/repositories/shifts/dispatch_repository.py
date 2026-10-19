"""asyncpg persistence for live_dispatches."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.shifts.dispatch_queries import (
    COUNT_DISPATCHES,
    DELETE_UNANSWERED_DISPATCHES,
    EXPIRE_DUE_OFFERS,
    INSERT_DISPATCHES,
    LIST_DISPATCH_CANDIDATES,
    LIST_OPEN_OFFERS_FOR_WORKER,
    LIST_WORKERS_NEAR_SCHEDULED,
    LOCK_DISPATCH,
    SET_DISPATCH_STATUS,
    UPSERT_ACCEPTED_DISPATCH,
    WITHDRAW_OPEN_OFFERS,
)


async def list_candidates(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    radius_km: float,
    require_verified: bool,
    fresh_since: datetime,
    lat_delta: float,
    lng_delta: float,
    business_user_id: UUID,
    limit: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        LIST_DISPATCH_CANDIDATES,
        shift["latitude"],
        shift["longitude"],
        radius_km,
        require_verified,
        fresh_since,
        lat_delta,
        lng_delta,
        shift["id"],
        business_user_id,
        shift["category_id"],
        shift["starts_at"],
        shift["ends_at"],
        limit,
    )


async def list_workers_near_scheduled(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    radius_km: float,
    require_verified: bool,
    lat_delta: float,
    lng_delta: float,
    business_user_id: UUID,
    limit: int,
) -> list[UUID]:
    rows = await conn.fetch(
        LIST_WORKERS_NEAR_SCHEDULED,
        shift["latitude"],
        shift["longitude"],
        radius_km,
        require_verified,
        lat_delta,
        lng_delta,
        business_user_id,
        shift["category_id"],
        limit,
    )
    return [r["user_id"] for r in rows]


async def insert_offers(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    radius_km: float,
    expires_at: datetime,
    worker_profile_ids: list[UUID],
    distances_km: list[float],
) -> list[UUID]:
    if not worker_profile_ids:
        return []
    rows = await conn.fetch(
        INSERT_DISPATCHES, shift_id, radius_km, expires_at, worker_profile_ids, distances_km
    )
    return [r["worker_profile_id"] for r in rows]


async def upsert_accepted(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    worker_profile_id: UUID,
    radius_km: float,
    distance_km: float,
    now: datetime,
) -> UUID | None:
    return await conn.fetchval(
        UPSERT_ACCEPTED_DISPATCH, shift_id, worker_profile_id, radius_km, distance_km, now
    )


async def lock_dispatch(
    conn: asyncpg.Connection, shift_id: UUID, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_DISPATCH, shift_id, worker_profile_id)


async def set_status(
    conn: asyncpg.Connection, dispatch_id: UUID, status: str, now: datetime
) -> None:
    await conn.execute(SET_DISPATCH_STATUS, dispatch_id, status, now)


async def withdraw_open_offers(conn: asyncpg.Connection, shift_id: UUID) -> list[UUID]:
    return [r["worker_profile_id"] for r in await conn.fetch(WITHDRAW_OPEN_OFFERS, shift_id)]


async def expire_due_offers(conn: asyncpg.Connection, now: datetime) -> int:
    result = await conn.execute(EXPIRE_DUE_OFFERS, now)
    return int(result.split()[-1])


async def delete_unanswered(conn: asyncpg.Connection, shift_id: UUID) -> None:
    await conn.execute(DELETE_UNANSWERED_DISPATCHES, shift_id)


async def count_dispatches(conn: asyncpg.Connection, shift_id: UUID) -> int:
    return int(await conn.fetchval(COUNT_DISPATCHES, shift_id))


async def list_open_offers_for_worker(
    conn: asyncpg.Connection, worker_profile_id: UUID, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_OPEN_OFFERS_FOR_WORKER, worker_profile_id, now)
