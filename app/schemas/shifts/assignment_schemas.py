"""Booked worker on a shift: roster, tracking, contact, chat, cancellation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.shifts.application_schemas import WorkerSummary
from app.schemas.shifts.shift_schemas import BusinessCard, WorkerShiftCard


class AttendanceSummary(BaseModel):
    checked_in_at: datetime | None = None
    check_in_distance_m: int | None = None
    checked_out_at: datetime | None = None
    worker_note: str = ""
    recorded_minutes: int | None = None
    approved_minutes: int | None = None
    business_note: str = ""
    approved_at: datetime | None = None


class RosterEntry(BaseModel):
    assignment_id: UUID
    status: str
    source: str
    confirmed_at: datetime
    travel_started_at: datetime | None = None
    late_cancellation: bool
    worker: WorkerSummary
    attendance: AttendanceSummary | None = None


class Roster(BaseModel):
    """Figma "Manage your confirmed roster"."""

    shift_id: UUID
    workers_required: int
    booked_count: int
    items: list[RosterEntry]


class RatingView(BaseModel):
    direction: str
    stars: int
    tags: list[str]
    review: str
    created_at: datetime


class AssignmentDetail(BaseModel):
    id: UUID
    status: str
    source: str
    hourly_rate_minor: int
    confirmed_at: datetime
    travel_started_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    late_cancellation: bool
    shift: WorkerShiftCard
    worker: WorkerSummary
    business: BusinessCard
    attendance: AttendanceSummary | None = None
    ratings: list[RatingView] = Field(default_factory=list)
    can_rate: bool = False
    check_in_opens_at: datetime


class TrackingPoint(BaseModel):
    latitude: float
    longitude: float
    recorded_at: datetime


class TrackingResponse(BaseModel):
    """Figma "Aarav is on the way · 8 min away"."""

    assignment_id: UUID
    status: str
    travel_started_at: datetime | None = None
    worker_location: TrackingPoint | None = None
    shift_latitude: float
    shift_longitude: float
    distance_km: float | None = None
    eta_minutes: int | None = None


class ContactResponse(BaseModel):
    name: str
    phone: str
    role: str


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=1000)


class MessageItem(BaseModel):
    id: UUID
    sender_user_id: UUID
    is_mine: bool
    body: str
    read_at: datetime | None = None
    created_at: datetime


class AssignmentCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=200)


class AssignmentCancelResponse(BaseModel):
    assignment_id: UUID
    status: str
    late_cancellation: bool
    shift_status: str
