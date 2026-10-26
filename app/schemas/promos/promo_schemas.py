"""Promo code request / response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.promos.promo_route_strings import PROMO_CODE_MAX_LENGTH


class PromoCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=PROMO_CODE_MAX_LENGTH)


class PromoView(BaseModel):
    id: UUID
    code: str
    discount_type: Literal["flat", "percent", "waive_fees"]
    discount_value: float = Field(description="₹ for flat, % for percent, 0 for waive_fees.")
    applies_to: Literal["commission", "gateway", "all_fees"]
    max_discount_minor: int | None
    valid_until: datetime | None
    is_voucher: bool = Field(description="Free-fees voucher issued to this business.")


class PromoList(BaseModel):
    items: list[PromoView]


class WorkerPromoStatus(BaseModel):
    """Code waiting to discount the commission on the worker's next payout."""

    pending: PromoView | None
