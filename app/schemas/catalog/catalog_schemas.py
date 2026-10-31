"""Reference data shown in pickers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RatingTags(BaseModel):
    direction: str
    tags: list[str]


class PaymentMethod(BaseModel):
    code: str
    label: str


class CancellationTier(BaseModel):
    party: str = Field(description="`business` or `worker`.")
    event: str = Field(description="`cancel`, `no_show` or `walk_off`.")
    hours_from: float = Field(description="Tier applies when at least this many hours remain.")
    hours_to: float | None = Field(description="Upper bound in hours; null means no limit.")
    flat_fee_minor: int
    booking_pct: float = Field(description="% of the booking amount charged.")
    fee_cap_minor: int | None
    worker_share_pct: float = Field(description="% of the booking amount paid to the worker.")
    strike_weight: float
    business_voucher: bool


class CancellationPolicy(BaseModel):
    version: int
    strike_window_days: int
    strikes_to_limit: float
    limit_days: int
    strikes_to_ban: float
    voucher_valid_days: int
    unfilled_cutoff_hours: int = Field(
        description="Seats still empty this many hours before start are refunded with a voucher.",
    )
    business_stop_worker_share_pct: int = Field(
        default=80,
        description="Business stops / force-cancels after the work started: the Worker keeps "
        "this % of the pay; the Business pays 100%.",
    )
    tiers: list[CancellationTier]


class FeePolicy(BaseModel):
    version: int
    percentage: float = Field(description="Business commission %.")
    worker_percentage: float = Field(description="Worker commission % (deducted from pay).")
    gateway_percentage: float = Field(description="Gateway charge % paid by the business.")
