"""Booked worker on a shift: roster, tracking, contact, chat, cancellation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attendance.attendance_schemas import CompletionCodeView, ExtensionView
from app.schemas.shifts.application_schemas import WorkerSummary
from app.schemas.shifts.shift_schemas import BusinessCard, CancellationQuote, WorkerShiftCard


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
    check_in_code: str | None = Field(default=None, description="Tell this worker on arrival.")
    extended_minutes: int = 0
    ended_reason: str | None = None
    completion_code: CompletionCodeView | None = Field(
        default=None, description="Give it to this worker when the work is done."
    )


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
    cancelled_by: str | None = Field(default=None, description="worker or business")
    cancel_reason: str | None = None
    late_cancellation: bool
    applied_at: datetime | None = None
    selected_at: datetime | None = None
    shift: WorkerShiftCard
    worker: WorkerSummary
    business: BusinessCard
    attendance: AttendanceSummary | None = None
    ratings: list[RatingView] = Field(default_factory=list)
    can_rate: bool = False
    check_in_opens_at: datetime
    check_in_code: str | None = Field(
        default=None, description="Business only: the worker enters it to check in."
    )
    ends_at: datetime = Field(description="Booked end plus accepted extensions.")
    extended_minutes: int = 0
    can_end: bool = Field(description="End time reached: either side can end without a PIN.")
    ended_reason: str | None = None
    early_end_requested_by: Literal["worker", "business"] | None = None
    early_end_pin: str | None = Field(
        default=None, description="Shown only to the side that did NOT ask to end early."
    )
    pending_extension: ExtensionView | None = None
    completion_code: CompletionCodeView | None = Field(
        default=None,
        description="While checked in. Business: the code to give the worker when the work is "
        "done. Worker: attempts left / locked (no code).",
    )


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
    charge: CancellationQuote | None = None
