"""asyncpg persistence for notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.repositories.notifications.notification_queries import (
    BUMP_PUSH_ATTEMPTS,
    CLAIM_PENDING_PUSHES,
    COUNT_UNREAD,
    INSERT_NOTIFICATION,
    INSERT_NOTIFICATIONS_BULK,
    LIST_NOTIFICATIONS,
    MARK_ALL_READ,
    MARK_READ,
    SET_PUSH_STATUS,
)


async def insert_notification(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    kind: str,
    title: str,
    body: str,
    data: dict[str, Any],
) -> UUID:
    return await conn.fetchval(INSERT_NOTIFICATION, user_id, kind, title, body, data)


async def insert_notifications_bulk(
    conn: asyncpg.Connection,
    *,
    user_ids: list[UUID],
    kind: str,
    title: str,
    body: str,
    data: dict[str, Any],
) -> None:
    if user_ids:
        await conn.execute(INSERT_NOTIFICATIONS_BULK, user_ids, kind, title, body, data)


async def list_notifications(
    conn: asyncpg.Connection, user_id: UUID, *, unread_only: bool, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_NOTIFICATIONS, user_id, unread_only, limit, offset)


async def count_unread(conn: asyncpg.Connection, user_id: UUID) -> int:
    return int(await conn.fetchval(COUNT_UNREAD, user_id))


async def mark_read(
    conn: asyncpg.Connection, notification_id: UUID, user_id: UUID, now: datetime
) -> bool:
    return (await conn.execute(MARK_READ, notification_id, user_id, now)).endswith(" 1")


async def mark_all_read(conn: asyncpg.Connection, user_id: UUID, now: datetime) -> None:
    await conn.execute(MARK_ALL_READ, user_id, now)


async def claim_pending_pushes(conn: asyncpg.Connection, limit: int) -> list[asyncpg.Record]:
    return await conn.fetch(CLAIM_PENDING_PUSHES, limit)


async def set_push_status(
    conn: asyncpg.Connection, ids: list[UUID], status: str, now: datetime
) -> None:
    if ids:
        await conn.execute(SET_PUSH_STATUS, ids, status, now)


async def bump_push_attempts(conn: asyncpg.Connection, ids: list[UUID]) -> None:
    """Leave the rows pending for the next sweep, one attempt closer to ``failed``."""
    if ids:
        await conn.execute(BUMP_PUSH_ATTEMPTS, ids)
