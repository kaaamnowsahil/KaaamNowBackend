"""Shift posting, Business / Work dashboard and worker discovery schemas.

Figma: "Tell us about the work", "When is the shift?", "Review and post", "Finding workers
nearby", Business / Work Home tabs, worker "Shifts near you" / shift detail / "My shifts".
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants.profiles.profile_route_strings import MSG_COORDINATES_PAIR
from app.constants.shifts.shift_route_strings import MAX_BULK_SHIFTS

ShiftType = Literal["live", "scheduled"]
ShiftStatus = Literal[
    "draft",
    "awaiting_payment",
    "searching",
    "open",
    "filled",
    "in_progress",
    "completed",
    "expired",
    "cancelled",
]


class _ShiftFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_slug: str | None = Field(default=None, max_length=64)
    job_title: str | None = Field(default=None, min_length=2, max_length=120)
    responsibilities: str | None = Field(default=None, max_length=4000)
    requirements: str | None = Field(default=None, max_length=4000)
    workers_required: int | None = Field(default=None, ge=1, le=100)
    hourly_rate_minor: int | None = Field(default=None, gt=0, le=10_000_000)
    starts_at: datetime | None = Field(default=None, description="Live shifts: omit to start now.")
    ends_at: datetime | None = None
    duration_minutes: int | None = Field(
        default=None, ge=60, le=16 * 60, description="Alternative to ends_at."
    )
    break_minutes: int | None = Field(default=None, ge=0, le=240)
    workplace_name: str | None = Field(default=None, max_length=160)
    address_text: str | None = Field(
        default=None, max_length=500, description="Defaults to the Business / Work address."
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    arrival_instructions: str | None = Field(default=None, max_length=2000)
    site_contact_name: str | None = Field(default=None, max_length=120)
    cancellation_cutoff_hours: int | None = Field(default=None, ge=0, le=72)

    @model_validator(mode="after")
    def _coordinates_pair(self):  # type: ignore[no-untyped-def]
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(MSG_COORDINATES_PAIR)
        return self


class ShiftCreate(_ShiftFields):
    business_profile_id: UUID | None = Field(
        default=None,
        description="Business / Work entity the shift is for. Defaults to the primary one.",
    )
    shift_type: ShiftType
    category_slug: str = Field(max_length=64)
    job_title: str = Field(min_length=2, max_length=120)
    workers_required: int = Field(ge=1, le=100)
    hourly_rate_minor: int = Field(gt=0, le=10_000_000, examples=[15000])
    publish: bool = Field(default=False, description="Create and post in one step.")
    promo_code: str | None = Field(
        default=None, max_length=32, description="Promo code or free-fees voucher."
    )


class ShiftPatch(_ShiftFields):
    """Draft-only edit. Omitted fields keep their value."""


class ShiftBulkItem(_ShiftFields):
    """One date in a multi-date posting; each date carries its own schedule and details."""

    category_slug: str = Field(max_length=64)
    job_title: str = Field(min_length=2, max_length=120, description="Role shown to workers.")
    workers_required: int = Field(ge=1, le=100)
    hourly_rate_minor: int = Field(gt=0, le=10_000_000, examples=[15000])
    starts_at: datetime
    break_minutes: int = Field(default=0, ge=0, le=240)


class ShiftBulkCreate(BaseModel):
    """Create several scheduled shifts at once. All are saved, or none are."""

    model_config = ConfigDict(extra="forbid")

    business_profile_id: UUID | None = Field(
        default=None,
        description="Business / Work entity for every shift. Defaults to the primary one.",
    )
    publish: bool = Field(default=False, description="Post all shifts; false saves drafts.")
    promo_code: str | None = Field(
        default=None, max_length=32, description="Applied to every date; each one uses the code."
    )
    shifts: list[ShiftBulkItem] = Field(min_length=1, max_length=MAX_BULK_SHIFTS)


class ShiftBulkPublish(BaseModel):
    """Post saved drafts by id. All are published, or none are."""

    model_config = ConfigDict(extra="forbid")

    shift_ids: list[UUID] = Field(min_length=1, max_length=MAX_BULK_SHIFTS)

    @model_validator(mode="after")
    def _unique(self):  # type: ignore[no-untyped-def]
        if len(set(self.shift_ids)) != len(self.shift_ids):
            raise ValueError("shift_ids must not contain duplicates.")
        return self


class ShiftEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hourly_rate_minor: int = Field(gt=0, le=10_000_000)
    workers_required: int = Field(ge=1, le=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=60, le=16 * 60)
    break_minutes: int = Field(default=0, ge=0, le=240)
    promo_code: str | None = Field(default=None, max_length=32)


class ShiftCostEstimate(BaseModel):
    """Figma "Estimated cost" card."""

    currency: str
    paid_minutes_per_worker: int
    pay_per_worker_minor: int
    workers_required: int
    worker_subtotal_minor: int
    fee_percentage: float = Field(description="Business commission %.")
    platform_fee_minor: int = Field(description="Business commission amount.")
    gateway_fee_percentage: float
    gateway_fee_minor: int
    total_minor: int = Field(
        description="What the business pays: pay + commission + gateway − promo discount."
    )
    promo_code: str | None = None
    promo_discount_minor: int = Field(
        default=0, description="Already taken off platform_fee_minor / gateway_fee_minor."
    )
    worker_fee_percentage: float
    worker_fee_per_worker_minor: int
    worker_net_per_worker_minor: int = Field(description="Worker take-home after commission.")


class ConvertToScheduledRequest(BaseModel):
    """Figma "No workers nearby → Post as scheduled shift"."""

    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    ends_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=60, le=16 * 60)


class ShiftCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=200)


class CancellationQuote(BaseModel):
    """Fee preview for one seat (also returned after the cancel). Amounts in paise."""

    party: Literal["worker", "business", "system"]
    event: Literal["cancel", "no_show", "walk_off", "unfilled"]
    hours_before: float
    booking_minor: int
    fee_minor: int = Field(description="Charged to the side that cancelled.")
    worker_compensation_minor: int = Field(description="Paid to the worker (business cancel).")
    business_refund_minor: int
    strike_weight: float
    business_voucher: bool = Field(description="Business gets a free-fees voucher.")
    seat_reopens: bool
    currency: str


class ShiftCancelPreview(BaseModel):
    """What cancelling the whole shift now would cost. Amounts in paise."""

    shift_id: UUID
    booked_workers: int
    fee_minor: int
    worker_compensation_minor: int
    business_refund_minor: int = Field(description="Back to the business from the deposit.")
    currency: str
    seats: list[CancellationQuote]


class LiveSearchState(BaseModel):
    search_radius_km: float | None = None
    max_search_radius_km: float | None = None
    search_started_at: datetime | None = None
    search_expires_at: datetime | None = None
    seconds_left: int = 0


class ShiftResponse(BaseModel):
    """Business / Work view of one shift."""

    id: UUID
    business_profile_id: UUID
    shift_type: ShiftType
    status: ShiftStatus
    category_slug: str
    category_name: str
    job_title: str
    responsibilities: str
    requirements: str
    workers_required: int
    hourly_rate_minor: int
    currency: str
    starts_at: datetime
    ends_at: datetime
    break_minutes: int
    workplace_name: str
    address_text: str
    latitude: float | None
    longitude: float | None
    arrival_instructions: str
    site_contact_name: str
    check_in_code: str = Field(description="Show at the venue; workers enter it to check in.")
    cancellation_cutoff_hours: int
    booked_count: int
    pending_applications: int
    withdrawn_count: int = Field(
        default=0, description="Workers who withdrew their application or booking, or declined."
    )
    estimate: ShiftCostEstimate
    live_search: LiveSearchState | None = None
    invoice_id: UUID | None = None
    deposit_invoice_id: UUID | None = Field(
        default=None, description="Pay this invoice to open an awaiting_payment shift."
    )
    deposit_status: str | None = None
    published_at: datetime | None = None
    filled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    created_at: datetime


class ShiftBulkResponse(BaseModel):
    items: list[ShiftResponse] = Field(description="Same order as the request.")


class ShiftListItem(BaseModel):
    id: UUID
    business_profile_id: UUID
    shift_type: ShiftType
    status: ShiftStatus
    job_title: str
    category_name: str
    workers_required: int
    booked_count: int
    checked_in_count: int
    pending_applications: int
    withdrawn_count: int = 0
    hourly_rate_minor: int
    currency: str
    starts_at: datetime
    ends_at: datetime
    cancellation_cutoff_hours: int
    estimate: ShiftCostEstimate
    workplace_name: str
    address_text: str
    invoice_status: str | None = None
    deposit_invoice_id: UUID | None = None
    deposit_status: str | None = None


ShiftGroupKey = Literal["upcoming", "in_progress", "draft", "completed", "expired", "cancelled"]


class BusinessShiftItem(ShiftListItem):
    group: ShiftGroupKey = Field(
        description=(
            "Server-computed section. upcoming: searching/open/filled and not yet ended. "
            "expired: expired, or still searching/open/filled after its end time. "
            "Other groups match status."
        )
    )


class ShiftGroupCount(BaseModel):
    key: ShiftGroupKey
    title: str = Field(examples=["Coming up"])
    count: int


class ShiftPage(BaseModel):
    items: list[BusinessShiftItem]
    group_counts: list[ShiftGroupCount] = Field(
        description=(
            "Always all six, in order: upcoming, in_progress, draft, completed, expired, "
            "cancelled. Counts honour shift_type and business_profile_id, not status/group."
        )
    )
    limit: int
    offset: int


class DashboardSummary(BaseModel):
    active_shifts: int
    workers_booked: int
    pending_applications: int
    awaiting_review: int
    unpaid_invoices: int


DashboardGroupKey = Literal["completed", "upcoming", "in_progress", "expired"]


class DashboardShift(ShiftListItem):
    dashboard_group: DashboardGroupKey = Field(
        description=(
            "Server-computed section. upcoming: searching/open/filled and not yet ended. "
            "in_progress: a worker has checked in. completed: shift finished. "
            "expired: expired, or still recruiting/filled after its end time."
        )
    )


class DashboardGroup(BaseModel):
    key: DashboardGroupKey
    title: str = Field(examples=["Coming up"])
    shifts: list[DashboardShift]


class DashboardResponse(BaseModel):
    """Business / Work Home: "Live now" / "Scheduled" tabs."""

    tab: Literal["live", "scheduled"]
    summary: DashboardSummary
    groups: list[DashboardGroup] = Field(
        description="Always all four, in order: completed, upcoming, in_progress, expired."
    )
    shifts: list[DashboardShift] = Field(description="Flat list in the same order as groups.")


class LiveSearchStatus(BaseModel):
    """Figma "Finding workers nearby" screen."""

    shift_id: UUID
    status: ShiftStatus
    workers_required: int
    accepted_count: int
    notified_count: int
    active_workers_nearby: int
    live_search: LiveSearchState
    can_convert_to_scheduled: bool
    can_retry: bool


class BusinessCard(BaseModel):
    id: UUID
    business_name: str
    logo_url: str | None = None
    rating_avg: float
    rating_count: int
    verification_status: str


class WorkerShiftCard(BaseModel):
    """Worker feed card."""

    id: UUID
    shift_type: ShiftType
    status: ShiftStatus
    job_title: str
    category_slug: str
    category_name: str
    business: BusinessCard
    workplace_name: str
    address_text: str
    latitude: float | None
    longitude: float | None
    distance_km: float | None = None
    starts_at: datetime
    ends_at: datetime
    break_minutes: int
    hourly_rate_minor: int
    currency: str
    estimated_pay_minor: int
    spots_left: int
    my_application_id: UUID | None = None
    my_application_status: str | None = None
    my_assignment_id: UUID | None = None
    my_assignment_status: str | None = None


class WorkerShiftDetail(WorkerShiftCard):
    responsibilities: str
    requirements: str
    arrival_instructions: str
    site_contact_name: str
    cancellation_cutoff_hours: int
    has_time_conflict: bool = Field(
        default=False,
        description="True when the worker already has another booking overlapping this shift.",
    )


class FeedPage(BaseModel):
    items: list[WorkerShiftCard]
    limit: int
    offset: int


class LiveRequestItem(BaseModel):
    """Figma "New request nearby · Accept within 04:59"."""

    dispatch_id: UUID
    expires_at: datetime
    seconds_left: int
    shift: WorkerShiftCard


class MyShiftItem(BaseModel):
    tab: str
    assignment_id: UUID | None = None
    assignment_status: str | None = None
    application_id: UUID | None = None
    application_status: str | None = None
    confirm_by: datetime | None = None
    applied_at: datetime | None = None
    decided_at: datetime | None = Field(
        default=None, description="When the business selected, rejected or it expired."
    )
    responded_at: datetime | None = Field(
        default=None, description="When the worker confirmed, declined or withdrew."
    )
    earned_minor: int | None = None
    shift: WorkerShiftCard


class MyShiftsPage(BaseModel):
    tab: Literal["upcoming", "active", "completed", "applications"]
    items: list[MyShiftItem]
    limit: int
    offset: int
