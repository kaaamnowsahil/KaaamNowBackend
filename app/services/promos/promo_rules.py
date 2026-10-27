"""Pure coupon maths (marketplace rules §3 promo codes, §9 free-fees voucher). No I/O.

A coupon only ever reduces platform fees (commission and / or gateway charge), never worker pay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.services.pricing.pricing_engine import Discounter, FeeDiscount
from app.utils.money import round_half_up

DISCOUNT_FLAT = "flat"
DISCOUNT_PERCENT = "percent"
DISCOUNT_WAIVE_FEES = "waive_fees"
APPLIES_COMMISSION = "commission"
APPLIES_GATEWAY = "gateway"
APPLIES_ALL_FEES = "all_fees"

BOOKING_SHIFT = "shift"
BOOKING_LIVE = "live"
BOOKING_ALL = "all"


@dataclass(frozen=True)
class Promo:
    id: object
    code: str
    discount_type: str
    discount_value: Decimal
    applies_to: str
    max_discount_minor: int | None

    @classmethod
    def from_row(cls, row) -> Promo:  # type: ignore[no-untyped-def]
        return cls(
            id=row["id"],
            code=row["code"],
            discount_type=row["discount_type"],
            discount_value=Decimal(row["discount_value"]),
            applies_to=row["applies_to"],
            max_discount_minor=row["max_discount_minor"],
        )


def promo_problem(  # type: ignore[no-untyped-def]
    row,
    *,
    role: str,
    user_id,
    now: datetime,
    user_uses: int,
    booking_type: str | None = None,
    amount_minor: int | None = None,
) -> str | None:
    """Why ``row`` can't be used right now, or None when it can. ``amount_minor`` is the work
    amount (worker pay before fees) checked against the coupon's minimum booking value."""
    if row is None or not row["is_active"]:
        return "not_found"
    if row["target_role"] != role:
        return "wrong_role"
    if row["owner_user_id"] is not None and row["owner_user_id"] != user_id:
        return "not_found"
    if now < row["valid_from"]:
        return "not_started"
    if row["valid_until"] is not None and now >= row["valid_until"]:
        return "expired"
    if row["max_uses"] is not None and row["used_count"] >= row["max_uses"]:
        return "used_up"
    if user_uses >= row["max_uses_per_user"]:
        return "already_used"
    if booking_type is not None and row["booking_types"] not in (BOOKING_ALL, booking_type):
        return "wrong_booking_type"
    if booking_type == BOOKING_LIVE and row["applies_to"] == APPLIES_GATEWAY:
        return "not_applicable"  # Live Work has no gateway charge to discount
    minimum = row["min_booking_minor"]
    if amount_minor is not None and minimum is not None and amount_minor < minimum:
        return "below_minimum"
    return None


def _discount(promo: Promo, base_minor: int, scale: Decimal) -> int:
    if base_minor <= 0:
        return 0
    if promo.discount_type == DISCOUNT_WAIVE_FEES:
        amount = base_minor
    elif promo.discount_type == DISCOUNT_PERCENT:
        amount = round_half_up(Decimal(base_minor) * promo.discount_value / Decimal(100))
    else:
        amount = round_half_up(promo.discount_value * Decimal(100) * scale)
    if promo.max_discount_minor is not None:
        amount = min(amount, round_half_up(Decimal(promo.max_discount_minor) * scale))
    return max(min(amount, base_minor), 0)


def fee_discount(
    promo: Promo, commission_minor: int, gateway_minor: int, *, scale: Decimal = Decimal(1)
) -> FeeDiscount:
    """``scale`` shares a flat amount / cap across seats (1 / seats for one seat's slice)."""
    if promo.applies_to == APPLIES_COMMISSION:
        return FeeDiscount(commission_minor=_discount(promo, commission_minor, scale))
    if promo.applies_to == APPLIES_GATEWAY:
        return FeeDiscount(gateway_minor=_discount(promo, gateway_minor, scale))
    off = _discount(promo, commission_minor + gateway_minor, scale)
    off_commission = min(off, commission_minor)
    return FeeDiscount(commission_minor=off_commission, gateway_minor=off - off_commission)


def discounter(promo: Promo | None, *, scale: Decimal = Decimal(1)) -> Discounter | None:
    if promo is None:
        return None
    return lambda commission, gateway: fee_discount(promo, commission, gateway, scale=scale)


def worker_commission_discount(promo: Promo, commission_minor: int) -> int:
    """Worker codes only ever discount the worker's commission on one payout."""
    return _discount(promo, commission_minor, Decimal(1))
