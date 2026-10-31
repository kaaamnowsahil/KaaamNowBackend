"""asyncpg persistence for shift_applications."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.shifts.application_queries import (
    CLOSE_OPEN_APPLICATIONS,
    COUNT_SELECTED,
    EXPIRE_DUE_SELECTIONS,
    GET_APPLICATION,
    GET_WORKER_APPLICATION,
    LIST_APPLICANTS,
    LIST_BUSINESS_APPLICANTS,
    LOCK_APPLICATION,
    REJECT_REMAINING_APPLIED,
    SET_APPLICATION_DECISION,
    SET_APPLICATION_RESPONSE,
    UPSERT_APPLICATION,
)


async def upsert_application(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    worker_profile_id: UUID,
    distance_km: float | None,
    cover_note: str,
    latitude: float | None = None,
    longitude: float | None = None,
) -> asyncpg.Record | None:
    """None when an active application already exists."""
    return await conn.fetchrow(
        UPSERT_APPLICATION,
        shift_id,
        worker_profile_id,
        distance_km,
        cover_note,
        latitude,
        longitude,
    )


async def get_worker_application(
    conn: asyncpg.Connection, shift_id: UUID, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WORKER_APPLICATION, shift_id, worker_profile_id)


async def lock_application(conn: asyncpg.Connection, application_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_APPLICATION, application_id)


async def get_application(conn: asyncpg.Connection, application_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_APPLICATION, application_id)


async def set_decision(
    conn: asyncpg.Connection,
    application_id: UUID,
    *,
    status: str,
    now: datetime,
    confirm_by: datetime | None,
) -> None:
    await conn.execute(SET_APPLICATION_DECISION, application_id, status, now, confirm_by)


async def set_response(
    conn: asyncpg.Connection, application_id: UUID, *, status: str, now: datetime
) -> None:
    await conn.execute(SET_APPLICATION_RESPONSE, application_id, status, now)


async def list_applicants(
    conn: asyncpg.Connection, shift_id: UUID, statuses: list[str] | None
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_APPLICANTS, shift_id, statuses)


async def list_business_applicants(
    conn: asyncpg.Connection,
    business_profile_ids: list[UUID],
    statuses: list[str],
    *,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_BUSINESS_APPLICANTS, business_profile_ids, statuses, limit, offset)


async def close_open_applications(
    conn: asyncpg.Connection, shift_id: UUID, *, status: str, now: datetime
) -> list[UUID]:
    rows = await conn.fetch(CLOSE_OPEN_APPLICATIONS, shift_id, status, now)
    return [r["worker_profile_id"] for r in rows]


async def reject_remaining_applied(
    conn: asyncpg.Connection, shift_id: UUID, now: datetime
) -> list[UUID]:
    return [
        r["worker_profile_id"] for r in await conn.fetch(REJECT_REMAINING_APPLIED, shift_id, now)
    ]


async def count_selected(conn: asyncpg.Connection, shift_id: UUID) -> int:
    return int(await conn.fetchval(COUNT_SELECTED, shift_id))


async def expire_due_selections(conn: asyncpg.Connection, now: datetime) -> list[asyncpg.Record]:
    return await conn.fetch(EXPIRE_DUE_SELECTIONS, now)
