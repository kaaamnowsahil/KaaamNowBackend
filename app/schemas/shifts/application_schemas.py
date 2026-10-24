"""Scheduled-shift applications (Figma "Apply", "Review applicants", "You've been selected")."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profiles.profile_schemas import _CoordinatesPair


class ApplicationCreate(_CoordinatesPair):
    model_config = ConfigDict(extra="forbid")

    cover_note: str = Field(default="", max_length=500)
    latitude: float | None = Field(
        default=None, ge=-90, le=90, description="Device's current location; not saved."
    )
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ApplicationResponse(BaseModel):
    id: UUID
    shift_id: UUID
    status: str
    distance_km: float | None = None
    cover_note: str
    confirm_by: datetime | None = None
    applied_at: datetime
    decided_at: datetime | None = None
    responded_at: datetime | None = None
    assignment_id: UUID | None = None


class WorkerSummary(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    photo_url: str | None = None
    rating_avg: float
    rating_count: int
    completed_shift_count: int
    verification_status: str


class ApplicantItem(BaseModel):
    application_id: UUID
    status: str
    applied_at: datetime
    confirm_by: datetime | None = None
    distance_km: float | None = None
    cover_note: str
    worker: WorkerSummary


class ApplicantList(BaseModel):
    shift_id: UUID
    workers_required: int
    booked_count: int
    items: list[ApplicantItem]
