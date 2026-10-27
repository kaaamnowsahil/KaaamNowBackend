"""Promo code (coupon) request / response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.promos.promo_route_strings import PROMO_CODE_MAX_LENGTH

BookingType = Literal["shift", "live"]
IneligibleReason = Literal[
    "not_found",
    "wrong_role",
    "not_started",
    "expired",
    "used_up",
    "already_used",
    "wrong_booking_type",
    "below_minimum",
    "not_applicable",
]


class PromoCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=PROMO_CODE_MAX_LENGTH)
    booking_type: BookingType | None = Field(
        default=None, description="Check the coupon against this kind of booking."
    )
    amount_minor: int | None = Field(
        default=None, ge=0, description="Work amount (worker pay before fees) in paise."
    )


class PromoView(BaseModel):
    id: UUID
    code: str
    title: str = ""
    discount_type: Literal["flat", "percent", "waive_fees"]
    discount_value: float = Field(description="₹ for flat, % for percent, 0 for waive_fees.")
    applies_to: Literal["commission", "gateway", "all_fees"]
    max_discount_minor: int | None
    min_booking_minor: int | None = None
    booking_types: Literal["all", "shift", "live"] = "all"
    valid_until: datetime | None
    is_voucher: bool = Field(description="Assigned to this Business only.")
    eligible: bool = True
    ineligible_reason: IneligibleReason | None = None
    message: str | None = Field(default=None, description="Why it can't be used, when it can't.")


class PromoList(BaseModel):
    items: list[PromoView]


class WorkerPromoStatus(BaseModel):
    """Code waiting to discount the commission on the worker's next payout."""

    pending: PromoView | None
