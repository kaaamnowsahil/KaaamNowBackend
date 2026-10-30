"""Live Work: Post Work, Live Work tracking, Accept Work, Extend Work, Complete Work."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.attendance.attendance_schemas import CompletionCodeView, completion_code_field

LiveWorkStatus = Literal[
    "awaiting_payment",
    "searching",
    "no_workers",
    "assigned",
    "en_route",
    "in_progress",
    "completed",
    "cancelled",
]
WorkerLiveStatus = Literal[
    "assigned", "en_route", "in_progress", "completed", "cancelled", "reassigned"
]
PricingMode = Literal["hourly", "task"]
ExtensionStatus = Literal[
    "requested", "awaiting_payment", "applied", "declined", "cancelled", "expired"
]


def _strip(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


def _check_live_pricing(
    mode: str, hourly_rate_minor: int | None, duration_minutes: int | None, task: int | None
) -> None:
    if mode == "task":
        if task is None:
            raise ValueError("task_price_minor is required for task pricing.")
    elif hourly_rate_minor is None or duration_minutes is None:
        raise ValueError("hourly_rate_minor and duration_minutes are required for hourly pricing.")


class _LivePricingFields(BaseModel):
    pricing_mode: PricingMode = Field(
        default="hourly",
        description="hourly: rate × Work Duration. task: one fixed price for the job, no "
        "duration, no extensions; finished with the completion code.",
    )
    hourly_rate_minor: int | None = Field(
        default=None, gt=0, le=10_000_000, description="Hourly: base rate per hour (paise)."
    )
    duration_minutes: int | None = Field(
        default=None, description="Hourly: Work Duration, 60–720 in 30-minute steps."
    )
    task_price_minor: int | None = Field(
        default=None, gt=0, le=10_000_000, description="Task: fixed price for the job (paise)."
    )

    @model_validator(mode="after")
    def _pricing(self):  # type: ignore[no-untyped-def]
        _check_live_pricing(
            self.pricing_mode, self.hourly_rate_minor, self.duration_minutes, self.task_price_minor
        )
        return self


# --- requests --------------------------------------------------------------------------


class LiveWorkQuoteRequest(_LivePricingFields):
    model_config = ConfigDict(extra="forbid")

    category_slug: str | None = Field(default=None, max_length=64)
    promo_code: str | None = Field(default=None, min_length=3, max_length=40)


class LiveWorkCreate(_LivePricingFields):
    model_config = ConfigDict(extra="forbid")

    business_profile_id: UUID | None = None
    category_slug: str = Field(min_length=1, max_length=64)
    job_title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=4000)
    address_text: str = Field(min_length=3, max_length=500, description="Work Location.")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    arrival_instructions: str = Field(default="", max_length=2000)
    site_contact_name: str = Field(default="", max_length=120)
    accept_terms: bool = Field(description="Business accepted the Live Work booking terms.")
    expected_total_minor: int | None = Field(
        default=None,
        ge=0,
        description="Total shown on the review screen; a different server total → 409.",
    )
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64)
    promo_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=40,
        description="Coupon chosen on Apply Coupon; validated and reserved by the server.",
    )

    _strip_text = field_validator(
        "job_title", "description", "address_text", "arrival_instructions", "site_contact_name"
    )(_strip)


class LiveExtensionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extra_minutes: int
    expected_total_minor: int | None = Field(default=None, ge=0)


class LiveExtensionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool


class LiveStartWork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arrival_code: str = Field(min_length=4, max_length=12)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: int | None = Field(default=None, ge=0, le=100_000)


class LiveCompleteWork(BaseModel):
    """Complete Work: the Worker enters the completion code shown in the Business app."""

    model_config = ConfigDict(extra="forbid")

    completion_code: str = completion_code_field()


class LiveLocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: int | None = Field(default=None, ge=0, le=100_000)


class LiveCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=300)
    expected_refund_minor: int | None = Field(
        default=None, ge=0, description="Refund shown in the preview; a different value → 409."
    )


# --- shared views ----------------------------------------------------------------------


class LivePriceBreakdown(BaseModel):
    currency: str
    settings_version: int
    pricing_mode: PricingMode = "hourly"
    hourly_rate_minor: int = Field(description="0 for task pricing.")
    reserved_minutes: int = Field(description="Task pricing: the day-of-work window, not billed.")
    task_price_minor: int | None = None
    base_amount_minor: int = Field(description="Rate × reserved duration, or the task price.")
    commission_pct: float
    commission_minor: int = Field(description="Platform commission (separate from tax).")
    promo_code: str | None = None
    promo_discount_minor: int = Field(
        default=0, description="Coupon discount; only reduces commission."
    )
    tax_label: str
    tax_pct: float
    tax_base: Literal["subtotal", "base_amount", "commission"]
    tax_base_description: str
    taxable_minor: int
    tax_minor: int
    total_minor: int = Field(description="Business pays: base + commission − coupon + tax.")
    worker_commission_minor: int
    worker_net_minor: int = Field(description="Worker receives: base − commission.")
    extension_surcharge_pct: float
    extension_rate_minor: int = Field(description="Hourly rate for extra time (incl. surcharge).")


class LiveWorkerDot(BaseModel):
    """Approximate (~110 m) position of an available worker; never identifies the worker."""

    latitude: float
    longitude: float


class LiveAvailableWorkers(BaseModel):
    count: int
    radius_km: float
    category_slug: str | None
    fresh_within_seconds: int
    checked_at: datetime
    workers: list[LiveWorkerDot] = Field(
        default_factory=list, description="Nearest available workers (max 50), for the map."
    )


class LiveWorkDetails(BaseModel):
    category_slug: str | None
    category_name: str | None
    job_title: str
    description: str
    address_text: str
    latitude: float | None = None
    longitude: float | None = None
    arrival_instructions: str
    site_contact_name: str
    business_name: str
    pricing_mode: PricingMode = "hourly"
    reserved_minutes: int
    hourly_rate_minor: int
    task_price_minor: int | None = None


class LiveSearchView(BaseModel):
    started_at: datetime | None
    expires_at: datetime | None
    seconds_left: int
    radius_km: float | None
    notified_workers: int
    available_workers: int


class LiveWorkerView(BaseModel):
    worker_id: UUID
    full_name: str | None
    photo_url: str | None
    rating_avg: float | None
    rating_count: int
    completed_shift_count: int
    verification_status: str


class LiveWorkerLocation(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: int | None
    recorded_at: datetime
    age_seconds: int
    is_stale: bool = Field(description="No update within the freshness window.")
    distance_km: float = Field(description="Straight-line distance to the Work Location.")


class LiveAssignmentView(BaseModel):
    assignment_id: UUID
    status: str
    accepted_at: datetime
    travel_started_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    ended_reason: str | None = Field(
        default=None, description="'worker_left' when the Worker stopped before the booked time."
    )
    worker: LiveWorkerView
    location: LiveWorkerLocation | None = Field(
        default=None, description="Only while the Worker is assigned and the booking is active."
    )
    location_status: Literal["live", "stale", "unavailable", "not_shared"]


class LiveArrivalCodeView(BaseModel):
    code: str
    expires_at: datetime
    attempts_left: int
    locked: bool
    expired: bool
    verified: bool


class LiveWorkerArrivalView(BaseModel):
    verified: bool
    attempts_left: int
    locked: bool
    expired: bool


class LiveTimerView(BaseModel):
    started_at: datetime | None
    ends_at: datetime | None
    reserved_minutes: int
    extended_minutes: int
    remaining_seconds: int | None
    completed_at: datetime | None


class LiveExtensionView(BaseModel):
    id: UUID
    status: ExtensionStatus
    extra_minutes: int
    hourly_rate_minor: int
    surcharge_pct: float
    extension_rate_minor: int
    base_amount_minor: int
    commission_pct: float
    commission_minor: int
    tax_pct: float
    tax_minor: int
    total_minor: int
    worker_net_minor: int
    invoice_id: UUID | None
    requested_at: datetime
    responded_at: datetime | None
    applied_at: datetime | None


class LiveExtensionQuote(BaseModel):
    original_minutes: int
    original_total_minor: int
    current_minutes: int = Field(description="Reserved + already applied extensions.")
    additional_minutes: int
    base_rate_minor: int
    surcharge_pct: float
    extension_rate_minor: int
    additional_base_minor: int
    commission_pct: float
    commission_minor: int
    tax_label: str
    tax_pct: float
    tax_minor: int
    additional_total_minor: int = Field(description="Payment required for this extension.")
    revised_minutes: int
    revised_total_minor: int
    currency: str


class LiveInvoiceSummary(BaseModel):
    id: UUID
    invoice_kind: str
    status: str
    total_minor: int
    amount_due_minor: int
    refund_due_minor: int
    paid_at: datetime | None


class LiveRefundView(BaseModel):
    id: UUID
    amount_minor: int
    status: Literal["pending", "processed", "failed"]
    reason: str
    created_at: datetime
    processed_at: datetime | None


class LiveCancellationView(BaseModel):
    cancelled_at: datetime | None
    cancelled_by: Literal["business", "worker", "system"] | None
    reason: str | None
    fee_minor: int
    refund_minor: int


class LiveCancelPreview(BaseModel):
    party: Literal["business", "worker"]
    stage: Literal["before_payment", "before_acceptance", "before_start", "during_work"]
    fee_minor: int
    worker_compensation_minor: int
    business_refund_minor: int
    business_retained_minor: int
    strike_weight: float
    business_voucher: bool
    rule: str = Field(description="Which documented rule applies.")
    effect: str
    currency: str


class BusinessLiveActions(BaseModel):
    can_pay: bool
    can_cancel: bool
    can_extend: bool
    can_end_work: bool
    can_reissue_code: bool
    can_repost: bool
    can_reissue_completion_code: bool = False


class WorkerLiveActions(BaseModel):
    can_start_travel: bool
    can_start_work: bool
    can_complete: bool
    can_cancel: bool
    can_answer_extension: bool


class BusinessLiveBooking(BaseModel):
    booking_id: UUID
    status: LiveWorkStatus
    shift_status: str
    server_time: datetime
    version: str = Field(description="Changes whenever anything visible changes.")
    created_at: datetime
    work: LiveWorkDetails
    pricing: LivePriceBreakdown
    search: LiveSearchView | None
    deposit_invoice: LiveInvoiceSummary | None
    assignment: LiveAssignmentView | None
    arrival_code: LiveArrivalCodeView | None
    completion_code: CompletionCodeView | None = Field(
        default=None, description="While working: give it to the Worker when the work is done."
    )
    timer: LiveTimerView | None
    extensions: list[LiveExtensionView]
    final_invoice: LiveInvoiceSummary | None
    refunds: list[LiveRefundView]
    cancellation: LiveCancellationView | None
    actions: BusinessLiveActions


class BusinessLiveBookingPage(BaseModel):
    items: list[BusinessLiveBooking]
    limit: int
    offset: int


class WorkerLiveEarnings(BaseModel):
    reserved_minutes: int
    base_amount_minor: int
    commission_pct: float
    worker_commission_minor: int
    worker_net_minor: int
    extension_net_minor: int
    total_net_minor: int


class WorkerLiveBooking(BaseModel):
    assignment_id: UUID
    booking_id: UUID
    status: WorkerLiveStatus
    server_time: datetime
    version: str
    work: LiveWorkDetails
    earnings: WorkerLiveEarnings
    arrival: LiveWorkerArrivalView | None
    completion: CompletionCodeView | None = Field(
        default=None, description="While working: attempts left for the completion code."
    )
    timer: LiveTimerView | None
    extensions: list[LiveExtensionView]
    cancellation: LiveCancellationView | None
    actions: WorkerLiveActions


class WorkerLiveRequest(BaseModel):
    booking_id: UUID
    dispatch_id: UUID
    job_title: str
    category_name: str | None
    business_name: str
    address_text: str
    distance_km: float | None
    pricing_mode: PricingMode = "hourly"
    reserved_minutes: int
    hourly_rate_minor: int
    task_price_minor: int | None = None
    worker_net_minor: int
    currency: str
    expires_at: datetime
    seconds_left: int


class WorkerActiveLiveWork(BaseModel):
    booking: WorkerLiveBooking | None


# --- admin -----------------------------------------------------------------------------


class LivePricingSettingsView(BaseModel):
    version: int
    commission_pct: float
    tax_pct: float
    tax_label: str
    tax_base: Literal["subtotal", "base_amount", "commission"]
    tax_base_description: str
    extension_surcharge_pct: float
    effective_from: datetime
    changed_by_label: str
    notes: str
    example: LivePriceBreakdown = Field(description="₹500/h × 2h priced with these settings.")


class LivePricingSettingsUpdate(BaseModel):
    """Numbers arrive as strings or numbers; each is validated to 0–100 with ≤2 decimals."""

    model_config = ConfigDict(extra="forbid")

    commission_pct: str | float | int
    tax_pct: str | float | int
    tax_label: str = Field(min_length=1, max_length=40)
    tax_base: Literal["subtotal", "base_amount", "commission"]
    extension_surcharge_pct: str | float | int
    notes: str = Field(default="", max_length=300)

    _strip_label = field_validator("tax_label", "notes")(_strip)


class LivePricingAuditItem(BaseModel):
    id: UUID
    settings_version: int
    field: str
    old_value: str | None
    new_value: str
    changed_by_user_id: UUID | None
    changed_by_label: str
    request_id: str | None
    changed_at: datetime


class LivePricingAuditPage(BaseModel):
    items: list[LivePricingAuditItem]
    total: int
    limit: int
    offset: int


class AdminLiveBookingItem(BaseModel):
    booking_id: UUID
    shift_status: str
    job_title: str
    category_name: str | None
    business_name: str
    worker_name: str | None
    assignment_status: str | None
    pricing_mode: PricingMode = "hourly"
    reserved_minutes: int
    task_price_minor: int | None = None
    total_minor: int
    commission_minor: int
    tax_minor: int
    refunded_minor: int
    open_refunds: int
    currency: str
    created_at: datetime


class AdminLiveBookingPage(BaseModel):
    items: list[AdminLiveBookingItem]
    total: int
    limit: int
    offset: int


class AdminLiveCancellation(BaseModel):
    party: str
    event: str
    fee_minor: int
    worker_compensation_minor: int
    business_refund_minor: int
    business_retained_minor: int
    strike_weight: float
    created_at: datetime


class AdminLiveRefund(BaseModel):
    id: UUID
    booking_id: UUID
    job_title: str
    amount_minor: int
    currency: str
    reason: str
    status: str
    provider: str
    provider_refund_id: str | None
    failure_reason: str | None
    attempts: int
    created_at: datetime
    processed_at: datetime | None


class AdminLiveRefundPage(BaseModel):
    items: list[AdminLiveRefund]
    total: int
    limit: int
    offset: int


class AdminLiveBookingDetail(BaseModel):
    """Admin view: no arrival code and no precise Worker location."""

    booking: AdminLiveBookingItem
    pricing: LivePriceBreakdown
    work_address: str
    assignment_status: str | None
    extensions: list[LiveExtensionView]
    invoices: list[LiveInvoiceSummary]
    refunds: list[AdminLiveRefund]
    cancellations: list[AdminLiveCancellation]
