"""Database operations for account deletion requests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.users import deletion_queries as q


async def create_request(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    return await conn.fetchrow(q.CREATE_REQUEST, user_id)


async def get_open_request(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_OPEN_REQUEST, user_id)


async def get_latest_request(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_LATEST_REQUEST, user_id)


async def get_request(conn: asyncpg.Connection, request_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_REQUEST, request_id)


async def lock_request(conn: asyncpg.Connection, request_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.LOCK_REQUEST, request_id)


async def list_requests(
    conn: asyncpg.Connection, status_filter: str | None, limit: int, offset: int
) -> tuple[list[asyncpg.Record], int]:
    items = await conn.fetch(q.LIST_REQUESTS, status_filter, limit, offset)
    total = await conn.fetchval(q.COUNT_REQUESTS, status_filter)
    return items, total


async def get_admin_request(conn: asyncpg.Connection, request_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.GET_ADMIN_REQUEST, request_id)


async def get_blocker_counts(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    return await conn.fetchrow(q.GET_BLOCKER_COUNTS, user_id)


async def list_active_holds(
    conn: asyncpg.Connection, request_id: UUID, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_ACTIVE_HOLDS, request_id, now)


async def list_events(conn: asyncpg.Connection, request_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_REQUEST_EVENTS, request_id)


async def add_event(
    conn: asyncpg.Connection,
    request_id: UUID,
    actor_user_id: UUID | None,
    event_type: str,
    details: dict[str, object],
) -> None:
    await conn.execute(q.INSERT_EVENT, request_id, actor_user_id, event_type, details)


async def add_hold(
    conn: asyncpg.Connection,
    request_id: UUID,
    basis: str,
    reason: str,
    reference: str | None,
    expires_at: datetime,
    actor_user_id: UUID,
) -> asyncpg.Record:
    return await conn.fetchrow(
        q.ADD_HOLD, request_id, basis, reason, reference, expires_at, actor_user_id
    )


async def set_request_on_hold(conn: asyncpg.Connection, request_id: UUID) -> None:
    await conn.execute(q.SET_REQUEST_ON_HOLD, request_id)


async def release_hold(
    conn: asyncpg.Connection,
    hold_id: UUID,
    request_id: UUID,
    released_at: datetime,
) -> bool:
    return await conn.fetchval(q.RELEASE_HOLD, hold_id, request_id, released_at) is not None


async def set_request_pending_if_no_holds(
    conn: asyncpg.Connection, request_id: UUID, now: datetime
) -> None:
    await conn.execute(q.SET_REQUEST_PENDING_IF_NO_HOLDS, request_id, now)


async def approve_request(conn: asyncpg.Connection, request_id: UUID, now: datetime) -> bool:
    return await conn.fetchval(q.APPROVE_REQUEST, request_id, now) is not None


async def lock_user(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(q.LOCK_USER, user_id)


async def lock_user_profiles(conn: asyncpg.Connection, user_id: UUID) -> None:
    await conn.fetch("SELECT id FROM business_profiles WHERE user_id = $1 FOR UPDATE", user_id)
    await conn.fetch("SELECT id FROM worker_profiles WHERE user_id = $1 FOR UPDATE", user_id)


async def anonymize_user(
    conn: asyncpg.Connection, user_id: UUID, phone: str, now: datetime
) -> None:
    await conn.execute(q.DELETE_USER_DEVICES, user_id)
    await conn.execute(q.DELETE_USER_NOTIFICATIONS, user_id)
    await conn.execute(q.DELETE_USER_OTP_CHALLENGES, phone)
    await conn.execute(q.DELETE_USER_REFRESH_TOKENS, user_id)
    await conn.execute(q.DELETE_WORKER_LOCATIONS, user_id)
    await conn.execute(q.DELETE_WORKER_CATEGORIES, user_id)
    await conn.execute(q.ANONYMIZE_PAYOUT_ACCOUNTS, user_id, now)
    await conn.execute(q.ANONYMIZE_WORKER_PROFILE, user_id, now)
    await conn.execute(q.ANONYMIZE_BUSINESS_PROFILE, user_id, now)
    await conn.execute(q.ANONYMIZE_ASSIGNMENT_MESSAGES, user_id)
    await conn.execute(q.ANONYMIZE_ATTENDANCE, user_id, now)
    await conn.execute(q.ANONYMIZE_SHIFTS, user_id, now)
    await conn.execute(q.ANONYMIZE_RATINGS, user_id)
    await conn.execute(q.ANONYMIZE_CLOSED_SUPPORT_TICKETS, user_id, now)
    await conn.execute(q.ANONYMIZE_USER, user_id, now)


async def lock_approved_requests(conn: asyncpg.Connection, limit: int) -> list[asyncpg.Record]:
    return await conn.fetch(q.LOCK_APPROVED_REQUESTS, limit)


async def complete_request(conn: asyncpg.Connection, request_id: UUID, now: datetime) -> bool:
    return await conn.fetchval(q.COMPLETE_REQUEST, request_id, now) is not None


async def lock_expired_holds(
    conn: asyncpg.Connection, now: datetime, limit: int
) -> list[asyncpg.Record]:
    return await conn.fetch(q.LIST_EXPIRED_HOLDS, now, limit)


async def mark_hold_expired(conn: asyncpg.Connection, hold_id: UUID) -> None:
    await conn.execute(q.MARK_HOLD_EXPIRED, hold_id)
