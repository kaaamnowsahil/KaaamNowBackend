"""asyncpg persistence for shift_assignments and assignment_messages."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.shifts.assignment_queries import (
    ADD_EXTENDED_MINUTES,
    CANCEL_ASSIGNMENT,
    CANCEL_SHIFT_ASSIGNMENTS,
    COUNT_ASSIGNMENTS_IN,
    EXPIRE_OPEN_EXTENSIONS,
    GET_ASSIGNMENT_CONTEXT,
    GET_BUSINESS_CONTACT,
    GET_EXTENSION,
    GET_OPEN_EXTENSION,
    GET_WORKER_SUMMARY,
    INSERT_ASSIGNMENT,
    INSERT_EXTENSION,
    INSERT_MESSAGE,
    LIST_EXTENSION_PROMPTS_DUE,
    LIST_EXTENSIONS,
    LIST_MESSAGES,
    LIST_ROSTER,
    LIST_SHIFT_ASSIGNMENTS,
    LIST_WORKER_USER_IDS_FOR_SHIFT,
    LOCK_ASSIGNMENT_CONTEXT,
    MARK_EXTENSION_PROMPTED,
    MARK_MESSAGES_READ,
    SET_ASSIGNMENT_STATUS,
    SET_EARLY_END_PIN,
    SET_ENDED,
    SET_EXTENSION_STATUS,
    START_TRAVEL,
    USER_IDS_FOR_WORKER_PROFILES,
)
from app.utils.references import new_check_in_code


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
        new_check_in_code(),
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


async def set_early_end_pin(
    conn: asyncpg.Connection,
    assignment_id: UUID,
    *,
    pin: str | None,
    requested_by: str | None,
    expires_at: datetime | None,
) -> None:
    await conn.execute(SET_EARLY_END_PIN, assignment_id, pin, requested_by, expires_at)


async def set_ended(conn: asyncpg.Connection, assignment_id: UUID, reason: str) -> None:
    await conn.execute(SET_ENDED, assignment_id, reason)


async def add_extended_minutes(conn: asyncpg.Connection, assignment_id: UUID, minutes: int) -> None:
    await conn.execute(ADD_EXTENDED_MINUTES, assignment_id, minutes)


async def insert_extension(
    conn: asyncpg.Connection,
    assignment_id: UUID,
    *,
    extra_minutes: int,
    requested_by_user_id: UUID,
    now: datetime,
) -> UUID:
    return await conn.fetchval(
        INSERT_EXTENSION, assignment_id, extra_minutes, requested_by_user_id, now
    )


async def lock_open_extension(
    conn: asyncpg.Connection, assignment_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_OPEN_EXTENSION, assignment_id)


async def lock_extension(conn: asyncpg.Connection, extension_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_EXTENSION, extension_id)


async def set_extension_status(
    conn: asyncpg.Connection, extension_id: UUID, status: str, now: datetime
) -> None:
    await conn.execute(SET_EXTENSION_STATUS, extension_id, status, now)


async def list_extensions(conn: asyncpg.Connection, assignment_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_EXTENSIONS, assignment_id)


async def expire_open_extensions(
    conn: asyncpg.Connection, assignment_id: UUID, now: datetime
) -> None:
    await conn.execute(EXPIRE_OPEN_EXTENSIONS, assignment_id, now)


async def list_extension_prompts_due(
    conn: asyncpg.Connection, start: datetime, end: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_EXTENSION_PROMPTS_DUE, start, end)


async def mark_extension_prompted(
    conn: asyncpg.Connection, assignment_ids: list[UUID], now: datetime
) -> None:
    await conn.execute(MARK_EXTENSION_PROMPTED, assignment_ids, now)
