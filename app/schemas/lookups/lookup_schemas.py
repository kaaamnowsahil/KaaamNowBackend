"""Lookup item (work category / business type) request and response models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.constants.lookups.lookup_route_strings import (
    ICON_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    SLUG_PATTERN,
)


class LookupItem(BaseModel):
    id: UUID
    slug: str
    name: str
    icon: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LookupCreate(BaseModel):
    slug: str = Field(max_length=SLUG_MAX_LENGTH, pattern=SLUG_PATTERN, examples=["barista"])
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH, examples=["Barista"])
    icon: str = Field(default="", max_length=ICON_MAX_LENGTH, examples=["coffee"])
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class LookupUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=SLUG_MAX_LENGTH, pattern=SLUG_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    icon: str | None = Field(default=None, max_length=ICON_MAX_LENGTH)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
