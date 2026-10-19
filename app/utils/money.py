"""Money maths in integer minor units (paise). Never use floats for amounts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def pay_for_minutes(hourly_rate_minor: int, minutes: int) -> int:
    """``rate × minutes / 60`` rounded half-up — e.g. 4 h × ₹150 = ₹600."""
    return round_half_up(Decimal(hourly_rate_minor) * Decimal(minutes) / Decimal(60))


def platform_fee(subtotal_minor: int, percentage: Decimal) -> int:
    """``round_half_up(subtotal × pct / 100)`` — e.g. 5% of ₹1,800 = ₹90."""
    return round_half_up(Decimal(subtotal_minor) * Decimal(percentage) / Decimal(100))
