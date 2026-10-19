"""Current user, preferences, roles and devices (Figma Profile / Language / Appearance)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ThemePreference = Literal["system", "light", "dark"]
SelfServiceRole = Literal["business", "worker"]
AnyRole = Literal["business", "worker", "admin"]
DevicePlatform = Literal["ios", "android", "web"]


class BusinessProfileSummary(BaseModel):
    id: UUID
    business_name: str
    verification_status: str


class WorkerProfileSummary(BaseModel):
    id: UUID
    verification_status: str
    is_available: bool


class MeResponse(BaseModel):
    id: UUID
    phone: str
    full_name: str
    email: str | None = None
    photo_url: str | None = None
    language_code: str
    theme_preference: ThemePreference
    active_role: AnyRole | None = None
    roles: list[AnyRole]
    business_profile: BusinessProfileSummary | None = None
    worker_profile: WorkerProfileSummary | None = None
    created_at: datetime


class MePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    language_code: str | None = Field(default=None, min_length=2, max_length=8)
    theme_preference: ThemePreference | None = None


class ActiveRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AnyRole


class AddRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: SelfServiceRole


class DeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: DevicePlatform
    push_token: str = Field(min_length=10, max_length=512)
    app_version: str = Field(default="", max_length=32)


class DeviceResponse(BaseModel):
    id: UUID
    platform: DevicePlatform
    app_version: str
    is_active: bool
    last_seen_at: datetime
