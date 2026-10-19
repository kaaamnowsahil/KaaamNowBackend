"""Notification centre schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationItem(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationItem]
    unread_count: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread_count: int
