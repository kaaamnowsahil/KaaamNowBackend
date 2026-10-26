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
    decided_at: datetime | None = Field(
        default=None, description="When the business selected or rejected, or it expired."
    )
    responded_at: datetime | None = Field(
        default=None, description="When the worker confirmed, declined or withdrew."
    )
    confirm_by: datetime | None = None
    distance_km: float | None = None
    cover_note: str
    worker: WorkerSummary
    assignment_id: UUID | None = Field(default=None, description="Set once the seat is booked.")


class ApplicantList(BaseModel):
    shift_id: UUID
    workers_required: int
    booked_count: int
    items: list[ApplicantItem]


class ApplicantShiftSummary(BaseModel):
    id: UUID
    shift_type: str
    status: str
    job_title: str
    workplace_name: str
    starts_at: datetime
    ends_at: datetime
    workers_required: int
    hourly_rate_minor: int
    currency: str


class BusinessApplicantItem(ApplicantItem):
    shift: ApplicantShiftSummary


class BusinessApplicantPage(BaseModel):
    status: str
    items: list[BusinessApplicantItem]
    limit: int
    offset: int
