"""Notification centre (Figma "Notifications")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.constants.application.application_common import SWAGGER_ROLE_ANY_USER, swagger_summary
from app.constants.notifications.notification_route_strings import (
    NOTIFICATIONS_ROUTE_PREFIX,
    OPENAPI_TAG_NOTIFICATIONS,
    PATH_READ_ALL,
    PATH_READ_ONE,
    PATH_UNREAD_COUNT,
)
from app.dependencies import CurrentUser
from app.schemas.notifications.notification_schemas import NotificationPage, UnreadCountResponse
from app.services.notifications import notification_service

router = APIRouter(prefix=NOTIFICATIONS_ROUTE_PREFIX, tags=[OPENAPI_TAG_NOTIFICATIONS])


@router.get(
    "",
    response_model=NotificationPage,
    summary=swagger_summary("List notifications", SWAGGER_ROLE_ANY_USER),
)
async def list_notifications(
    user: CurrentUser,
    unread_only: bool = False,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> NotificationPage:
    return await notification_service.list_notifications(
        user, unread_only=unread_only, limit=limit, offset=offset
    )


@router.get(
    PATH_UNREAD_COUNT,
    response_model=UnreadCountResponse,
    summary=swagger_summary("Unread notification count", SWAGGER_ROLE_ANY_USER),
)
async def unread_count(user: CurrentUser) -> UnreadCountResponse:
    return await notification_service.unread_count(user)


@router.post(
    PATH_READ_ALL,
    response_model=UnreadCountResponse,
    summary=swagger_summary("Mark all notifications read", SWAGGER_ROLE_ANY_USER),
)
async def mark_all_read(user: CurrentUser) -> UnreadCountResponse:
    return await notification_service.mark_all_read(user)


@router.post(
    PATH_READ_ONE,
    response_model=UnreadCountResponse,
    summary=swagger_summary("Mark notification read", SWAGGER_ROLE_ANY_USER),
)
async def mark_read(notification_id: UUID, user: CurrentUser) -> UnreadCountResponse:
    return await notification_service.mark_read(user, notification_id)
