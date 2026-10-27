"""Live Work pricing — pure functions over integer paise (no I/O).

For a booking of ``reserved_minutes`` at ``hourly_rate`` with the active (or snapshotted) rates:

    base        = round_half_up(hourly_rate × reserved_minutes / 60)
    commission  = round_half_up(base × commission_pct / 100)          # platform commission
    taxable     = base + commission   (tax_base 'subtotal', default)
                | base                (tax_base 'base_amount')
                | commission          (tax_base 'commission')
    tax         = round_half_up(taxable × tax_pct / 100)
    total       = base + commission + tax                             # what the Business pays
    worker_net  = base − round_half_up(base × commission_pct / 100)   # what the Worker earns

Extension of ``extra_minutes`` (surcharge from the booking snapshot):

    extension_rate = round_half_up(hourly_rate × (100 + surcharge_pct) / 100)
    base           = round_half_up(hourly_rate × extra_minutes × (100 + surcharge_pct) / 6000)
    commission / tax / total / worker_net as above on that base.

All amounts come from the shared engine (app.services.pricing.pricing_engine). A Business coupon
only reduces the booking's commission (Live Work has no gateway charge) and never applies to
extensions.

Reserved time is always billed in full, even when work finishes early.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.pricing.pricing_engine import (
    DEFAULT_COMMISSION_PCT,
    DEFAULT_TAX_PCT,
    TAX_BASE_BASE_AMOUNT,
    TAX_BASE_COMMISSION,
    TAX_BASE_SUBTOTAL,
    TAX_BASES,
    FeeDiscount,
    InvalidPercentage,
    PricingRates,
    compute_charge,
    parse_percentage,
    taxable_amount,
)
from app.services.promos.promo_rules import Promo, discounter
from app.utils.money import pay_for_minutes, platform_fee, round_half_up

__all__ = [
    "DEFAULT_COMMISSION_PCT",
    "DEFAULT_TAX_PCT",
    "TAX_BASES",
    "TAX_BASE_BASE_AMOUNT",
    "TAX_BASE_COMMISSION",
    "TAX_BASE_SUBTOTAL",
    "InvalidPercentage",
    "parse_percentage",
    "taxable_amount",
]

DEFAULT_EXTENSION_SURCHARGE_PCT = Decimal("30.00")

MIN_RESERVED_MINUTES = 60
MAX_RESERVED_MINUTES = 12 * 60
RESERVED_MINUTES_STEP = 30
MIN_EXTENSION_MINUTES = 30
MAX_EXTENSION_MINUTES = 4 * 60
EXTENSION_MINUTES_STEP = 30


@dataclass(frozen=True)
class LiveRates:
    version: int
    commission_pct: Decimal
    tax_pct: Decimal
    tax_label: str
    tax_base: str
    extension_surcharge_pct: Decimal


@dataclass(frozen=True)
class LiveCharge:
    """``commission_minor`` is the full commission; ``discount_minor`` (coupon) comes off it
    and tax is worked out on the discounted amount."""

    base_amount_minor: int
    commission_minor: int
    taxable_minor: int
    tax_minor: int
    worker_commission_minor: int
    discount_minor: int = 0

    @property
    def net_commission_minor(self) -> int:
        return self.commission_minor - self.discount_minor

    @property
    def total_minor(self) -> int:
        return self.base_amount_minor + self.net_commission_minor + self.tax_minor

    @property
    def worker_net_minor(self) -> int:
        return self.base_amount_minor - self.worker_commission_minor


def charge_for_base(
    base_minor: int,
    *,
    commission_pct: Decimal,
    tax_pct: Decimal,
    tax_base: str,
    promo: Promo | None = None,
    discount_minor: int = 0,
) -> LiveCharge:
    """``promo`` prices a new booking; ``discount_minor`` re-applies a snapshotted coupon
    amount (capped at the commission)."""
    discount = discounter(promo)
    if discount is None and discount_minor:
        discount = lambda commission, _gateway: FeeDiscount(min(discount_minor, commission))  # noqa: E731
    charge = compute_charge(
        base_minor,
        PricingRates(commission_pct=commission_pct, tax_pct=tax_pct, tax_base=tax_base),
        discount,
    )
    return LiveCharge(
        base_amount_minor=base_minor,
        commission_minor=charge.commission_minor,
        taxable_minor=charge.taxable_minor,
        tax_minor=charge.tax_minor,
        worker_commission_minor=platform_fee(base_minor, commission_pct),
        discount_minor=charge.commission_discount_minor,
    )


def booking_charge(
    hourly_rate_minor: int, reserved_minutes: int, rates: LiveRates, promo: Promo | None = None
) -> LiveCharge:
    return charge_for_base(
        pay_for_minutes(hourly_rate_minor, reserved_minutes),
        commission_pct=rates.commission_pct,
        tax_pct=rates.tax_pct,
        tax_base=rates.tax_base,
        promo=promo,
    )


def extension_rate(hourly_rate_minor: int, surcharge_pct: Decimal) -> int:
    return round_half_up(Decimal(hourly_rate_minor) * (Decimal(100) + surcharge_pct) / 100)


def extension_base(hourly_rate_minor: int, extra_minutes: int, surcharge_pct: Decimal) -> int:
    return round_half_up(
        Decimal(hourly_rate_minor)
        * Decimal(extra_minutes)
        * (Decimal(100) + surcharge_pct)
        / Decimal(6000)
    )


def extension_charge(
    hourly_rate_minor: int,
    extra_minutes: int,
    *,
    surcharge_pct: Decimal,
    commission_pct: Decimal,
    tax_pct: Decimal,
    tax_base: str,
) -> LiveCharge:
    return charge_for_base(
        extension_base(hourly_rate_minor, extra_minutes, surcharge_pct),
        commission_pct=commission_pct,
        tax_pct=tax_pct,
        tax_base=tax_base,
    )


def worked_charge(
    hourly_rate_minor: int,
    worked_minutes: int,
    *,
    commission_pct: Decimal,
    tax_pct: Decimal,
    tax_base: str,
    promo: Promo | None = None,
) -> LiveCharge:
    """Pro-rata charge for time actually worked (Worker stopped mid-booking)."""
    return charge_for_base(
        pay_for_minutes(hourly_rate_minor, worked_minutes),
        commission_pct=commission_pct,
        tax_pct=tax_pct,
        tax_base=tax_base,
        promo=promo,
    )


def validate_reserved_minutes(minutes: int) -> str | None:
    if minutes < MIN_RESERVED_MINUTES:
        return f"Minimum duration is {MIN_RESERVED_MINUTES // 60} hour."
    if minutes > MAX_RESERVED_MINUTES:
        return f"Maximum duration is {MAX_RESERVED_MINUTES // 60} hours."
    if minutes % RESERVED_MINUTES_STEP:
        return f"Duration must be in steps of {RESERVED_MINUTES_STEP} minutes."
    return None


def validate_extension_minutes(minutes: int) -> str | None:
    if minutes < MIN_EXTENSION_MINUTES:
        return f"Minimum extension is {MIN_EXTENSION_MINUTES} minutes."
    if minutes > MAX_EXTENSION_MINUTES:
        return f"Maximum extension is {MAX_EXTENSION_MINUTES // 60} hours."
    if minutes % EXTENSION_MINUTES_STEP:
        return f"Extension must be in steps of {EXTENSION_MINUTES_STEP} minutes."
    return None


def prorated_discount(discount_minor: int, *, reserved_base_minor: int, base_minor: int) -> int:
    """Share of a booking coupon kept when only part of the reserved time is billed."""
    if not discount_minor or reserved_base_minor <= 0:
        return 0
    if base_minor >= reserved_base_minor:
        return discount_minor
    return round_half_up(Decimal(discount_minor) * base_minor / reserved_base_minor)


def completed_charge(
    booking: LiveCharge, extensions: list[LiveCharge], commission_pct: Decimal
) -> LiveCharge:
    """Final bill: the booking snapshot (with its coupon) plus applied extensions (never
    discounted). Each part was already taxed at its own snapshot rate."""
    if not extensions:
        return booking
    base = booking.base_amount_minor + sum(e.base_amount_minor for e in extensions)
    return LiveCharge(
        base_amount_minor=base,
        commission_minor=booking.commission_minor + sum(e.commission_minor for e in extensions),
        taxable_minor=booking.taxable_minor + sum(e.taxable_minor for e in extensions),
        tax_minor=booking.tax_minor + sum(e.tax_minor for e in extensions),
        worker_commission_minor=platform_fee(base, commission_pct),
        discount_minor=booking.discount_minor,
    )
