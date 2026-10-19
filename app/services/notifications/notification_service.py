"""In-app notification centre. Writers call ``notify`` inside their own transaction."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.constants.notifications.notification_route_strings import MSG_NOTIFICATION_NOT_FOUND
from app.db.pool import get_pool
from app.exceptions.api_errors import not_found
from app.pagination import clamp_page_limit
from app.repositories.notifications import notification_repository
from app.schemas.notifications.notification_schemas import (
    NotificationItem,
    NotificationPage,
    UnreadCountResponse,
)
from app.security.authenticated_user import AuthenticatedUser
from app.utils.clock import utc_now


def _payload(kind: str, data: dict[str, Any] | None) -> dict[str, Any]:
    return {"kind": kind, **{k: str(v) if isinstance(v, UUID) else v for k, v in (data or {}).items()}}


async def notify(
    conn: asyncpg.Connection,
    user_id: UUID,
    kind: str,
    title: str,
    body: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    await notification_repository.insert_notification(
        conn, user_id=user_id, kind=kind, title=title, body=body, data=_payload(kind, data)
    )


async def notify_many(
    conn: asyncpg.Connection,
    user_ids: list[UUID],
    kind: str,
    title: str,
    body: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    await notification_repository.insert_notifications_bulk(
        conn, user_ids=user_ids, kind=kind, title=title, body=body, data=_payload(kind, data)
    )


async def list_notifications(
    user: AuthenticatedUser, *, unread_only: bool, limit: int | None, offset: int
) -> NotificationPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        rows = await notification_repository.list_notifications(
            conn, user.user_id, unread_only=unread_only, limit=page_limit, offset=offset
        )
        unread = await notification_repository.count_unread(conn, user.user_id)
    return NotificationPage(
        items=[NotificationItem.model_validate(dict(r)) for r in rows],
        unread_count=unread,
        limit=page_limit,
        offset=offset,
    )


async def unread_count(user: AuthenticatedUser) -> UnreadCountResponse:
    async with get_pool().acquire() as conn:
        return UnreadCountResponse(
            unread_count=await notification_repository.count_unread(conn, user.user_id)
        )


async def mark_read(user: AuthenticatedUser, notification_id: UUID) -> UnreadCountResponse:
    async with get_pool().acquire() as conn:
        if not await notification_repository.mark_read(
            conn, notification_id, user.user_id, utc_now()
        ):
            raise not_found("notification_not_found", MSG_NOTIFICATION_NOT_FOUND)
        return UnreadCountResponse(
            unread_count=await notification_repository.count_unread(conn, user.user_id)
        )


async def mark_all_read(user: AuthenticatedUser) -> UnreadCountResponse:
    async with get_pool().acquire() as conn:
        await notification_repository.mark_all_read(conn, user.user_id, utc_now())
    return UnreadCountResponse(unread_count=0)
