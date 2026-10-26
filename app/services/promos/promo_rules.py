"""Pure promo maths (marketplace rules §3 promo codes, §9 free-fees voucher). No I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.utils.money import BusinessCharge, round_half_up

DISCOUNT_FLAT = "flat"
DISCOUNT_PERCENT = "percent"
DISCOUNT_WAIVE_FEES = "waive_fees"
APPLIES_COMMISSION = "commission"
APPLIES_GATEWAY = "gateway"
APPLIES_ALL_FEES = "all_fees"


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


def promo_problem(row, *, role: str, user_id, now: datetime, user_uses: int) -> str | None:  # type: ignore[no-untyped-def]
    """Why ``row`` can't be used right now, or None when it can."""
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


def discount_charge(
    charge: BusinessCharge, promo: Promo | None, *, scale: Decimal = Decimal(1)
) -> tuple[BusinessCharge, int]:
    """Take the promo off commission and / or gateway (never off worker pay). ``scale``
    shares a flat amount / cap across seats (1 / seats for one seat's slice)."""
    if promo is None:
        return charge, 0
    commission, gateway = charge.commission_minor, charge.gateway_fee_minor
    if promo.applies_to == APPLIES_COMMISSION:
        off = _discount(promo, commission, scale)
        return BusinessCharge(charge.worker_subtotal_minor, commission - off, gateway), off
    if promo.applies_to == APPLIES_GATEWAY:
        off = _discount(promo, gateway, scale)
        return BusinessCharge(charge.worker_subtotal_minor, commission, gateway - off), off
    off = _discount(promo, commission + gateway, scale)
    off_commission = min(off, commission)
    return (
        BusinessCharge(
            charge.worker_subtotal_minor,
            commission - off_commission,
            gateway - (off - off_commission),
        ),
        off,
    )


def worker_commission_discount(promo: Promo, commission_minor: int) -> int:
    """Worker codes only ever discount the worker's commission on one payout."""
    return _discount(promo, commission_minor, Decimal(1))
