"""Money maths in integer minor units (paise). Never use floats for amounts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def pay_for_minutes(hourly_rate_minor: int, minutes: int) -> int:
    """``rate × minutes / 60`` rounded half-up — e.g. 4 h × ₹150 = ₹600."""
    return round_half_up(Decimal(hourly_rate_minor) * Decimal(minutes) / Decimal(60))


def overtime_pay(hourly_rate_minor: int, minutes: int, rate_pct: int) -> int:
    """Overtime minutes at ``rate_pct`` of the hourly rate (130 = 1.3×)."""
    return round_half_up(
        Decimal(hourly_rate_minor) * Decimal(minutes) * Decimal(rate_pct) / Decimal(6000)
    )


def platform_fee(subtotal_minor: int, percentage: Decimal) -> int:
    """``round_half_up(subtotal × pct / 100)`` — e.g. 5% of ₹1,800 = ₹90."""
    return round_half_up(Decimal(subtotal_minor) * Decimal(percentage) / Decimal(100))


@dataclass(frozen=True)
class FeeRates:
    """Business commission + gateway charge are added for the business; worker commission is
    deducted from worker pay."""

    business_pct: Decimal
    worker_pct: Decimal
    gateway_pct: Decimal


@dataclass(frozen=True)
class BusinessCharge:
    worker_subtotal_minor: int
    commission_minor: int
    gateway_fee_minor: int

    @property
    def total_minor(self) -> int:
        return self.worker_subtotal_minor + self.commission_minor + self.gateway_fee_minor


def business_charge(worker_subtotal_minor: int, rates: FeeRates) -> BusinessCharge:
    """Gateway is charged on everything the business pays (pay + commission)."""
    commission = platform_fee(worker_subtotal_minor, rates.business_pct)
    gateway = platform_fee(worker_subtotal_minor + commission, rates.gateway_pct)
    return BusinessCharge(worker_subtotal_minor, commission, gateway)


def worker_commission(pay_minor: int, rates: FeeRates) -> int:
    return platform_fee(pay_minor, rates.worker_pct)
