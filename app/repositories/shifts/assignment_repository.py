"""asyncpg persistence for shift_assignments and assignment_messages."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.shifts.assignment_queries import (
    CANCEL_ASSIGNMENT,
    CANCEL_SHIFT_ASSIGNMENTS,
    COUNT_ASSIGNMENTS_IN,
    GET_ASSIGNMENT_CONTEXT,
    GET_BUSINESS_CONTACT,
    GET_WORKER_SUMMARY,
    INSERT_ASSIGNMENT,
    INSERT_MESSAGE,
    LIST_MESSAGES,
    LIST_ROSTER,
    LIST_SHIFT_ASSIGNMENTS,
    LIST_WORKER_USER_IDS_FOR_SHIFT,
    LOCK_ASSIGNMENT_CONTEXT,
    MARK_MESSAGES_READ,
    SET_ASSIGNMENT_STATUS,
    START_TRAVEL,
    USER_IDS_FOR_WORKER_PROFILES,
)


async def insert_assignment(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    worker_profile_id: UUID,
    source: str,
    dispatch_id: UUID | None,
    application_id: UUID | None,
    hourly_rate_minor: int,
    now: datetime,
) -> UUID:
    return await conn.fetchval(
        INSERT_ASSIGNMENT,
        shift_id,
        worker_profile_id,
        source,
        dispatch_id,
        application_id,
        hourly_rate_minor,
        now,
    )


async def get_context(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_ASSIGNMENT_CONTEXT, assignment_id)


async def lock_context(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_ASSIGNMENT_CONTEXT, assignment_id)


async def list_roster(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_ROSTER, shift_id)


async def get_worker_summary(
    conn: asyncpg.Connection, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WORKER_SUMMARY, worker_profile_id)


async def get_business_contact(
    conn: asyncpg.Connection, business_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BUSINESS_CONTACT, business_profile_id)


async def set_status(conn: asyncpg.Connection, assignment_id: UUID, status: str) -> None:
    await conn.execute(SET_ASSIGNMENT_STATUS, assignment_id, status)


async def start_travel(conn: asyncpg.Connection, assignment_id: UUID, now: datetime) -> None:
    await conn.execute(START_TRAVEL, assignment_id, now)


async def cancel_assignment(
    conn: asyncpg.Connection,
    assignment_id: UUID,
    *,
    now: datetime,
    actor_user_id: UUID,
    reason: str,
    late: bool,
) -> None:
    await conn.execute(CANCEL_ASSIGNMENT, assignment_id, now, actor_user_id, reason, late)


async def cancel_shift_assignments(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    now: datetime,
    actor_user_id: UUID,
    reason: str,
    late: bool,
) -> list[UUID]:
    rows = await conn.fetch(CANCEL_SHIFT_ASSIGNMENTS, shift_id, now, actor_user_id, reason, late)
    return [r["worker_profile_id"] for r in rows]


async def list_worker_user_ids(
    conn: asyncpg.Connection, shift_id: UUID, statuses: list[str]
) -> list[UUID]:
    return [
        r["user_id"] for r in await conn.fetch(LIST_WORKER_USER_IDS_FOR_SHIFT, shift_id, statuses)
    ]


async def user_ids_for_worker_profiles(
    conn: asyncpg.Connection, worker_profile_ids: list[UUID]
) -> list[UUID]:
    if not worker_profile_ids:
        return []
    return [
        r["user_id"] for r in await conn.fetch(USER_IDS_FOR_WORKER_PROFILES, worker_profile_ids)
    ]


async def count_in(conn: asyncpg.Connection, shift_id: UUID, statuses: list[str]) -> int:
    return int(await conn.fetchval(COUNT_ASSIGNMENTS_IN, shift_id, statuses))


async def list_shift_assignments(conn: asyncpg.Connection, shift_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_SHIFT_ASSIGNMENTS, shift_id)


async def insert_message(
    conn: asyncpg.Connection, assignment_id: UUID, sender_user_id: UUID, body: str
) -> asyncpg.Record:
    return await conn.fetchrow(INSERT_MESSAGE, assignment_id, sender_user_id, body)


async def list_messages(
    conn: asyncpg.Connection, assignment_id: UUID, *, after: datetime | None, limit: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_MESSAGES, assignment_id, after, limit)


async def mark_messages_read(
    conn: asyncpg.Connection, assignment_id: UUID, reader_user_id: UUID, now: datetime
) -> None:
    await conn.execute(MARK_MESSAGES_READ, assignment_id, reader_user_id, now)
