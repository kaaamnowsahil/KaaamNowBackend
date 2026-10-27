"""The one price calculation for every booking type (Shift and Live Work). Integer paise, no I/O.

    commission = round_half_up(base × commission_pct / 100)
    gateway    = round_half_up((base + commission) × gateway_pct / 100)     # Shift only today
    discount   = coupon on the platform fees (commission and / or gateway), never on worker pay
    taxable    = base + (commission − commission_discount)   tax_base 'subtotal' (default)
               | base                                        tax_base 'base_amount'
               | commission − commission_discount            tax_base 'commission'
    tax        = round_half_up(taxable × tax_pct / 100)
    total      = base + (commission − commission_discount) + (gateway − gateway_discount) + tax

The gateway charge is a payment-processing cost, not a platform service, so it is never part of
the taxable amount. A coupon lowers the fee before tax is worked out.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.utils.money import platform_fee

TAX_BASE_SUBTOTAL = "subtotal"
TAX_BASE_BASE_AMOUNT = "base_amount"
TAX_BASE_COMMISSION = "commission"
TAX_BASES = (TAX_BASE_SUBTOTAL, TAX_BASE_BASE_AMOUNT, TAX_BASE_COMMISSION)

DEFAULT_COMMISSION_PCT = Decimal("4.00")
DEFAULT_TAX_PCT = Decimal("2.00")
DEFAULT_TAX_LABEL = "Tax"
DEFAULT_TAX_BASE = TAX_BASE_SUBTOTAL


class InvalidPercentage(ValueError):
    pass


def parse_percentage(value: object) -> Decimal:
    """0–100 with at most two decimals; rejects blanks, NaN, infinities and non-numbers."""
    if isinstance(value, bool) or value is None:
        raise InvalidPercentage("Enter a number between 0 and 100.")
    try:
        pct = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise InvalidPercentage("Enter a number between 0 and 100.") from exc
    if not pct.is_finite():
        raise InvalidPercentage("Enter a number between 0 and 100.")
    if pct < 0 or pct > 100:
        raise InvalidPercentage("Must be between 0 and 100.")
    if pct.as_tuple().exponent < -2:  # type: ignore[operator]
        raise InvalidPercentage("Use at most two decimal places.")
    return pct.quantize(Decimal("0.01"))


def taxable_amount(base_minor: int, commission_minor: int, tax_base: str) -> int:
    if tax_base == TAX_BASE_SUBTOTAL:
        return base_minor + commission_minor
    if tax_base == TAX_BASE_BASE_AMOUNT:
        return base_minor
    if tax_base == TAX_BASE_COMMISSION:
        return commission_minor
    raise ValueError(f"unknown tax base {tax_base!r}")


@dataclass(frozen=True)
class PricingRates:
    commission_pct: Decimal
    tax_pct: Decimal = Decimal(0)
    tax_base: str = DEFAULT_TAX_BASE
    gateway_pct: Decimal = Decimal(0)


@dataclass(frozen=True)
class FeeDiscount:
    commission_minor: int = 0
    gateway_minor: int = 0

    @property
    def total_minor(self) -> int:
        return self.commission_minor + self.gateway_minor


Discounter = Callable[[int, int], FeeDiscount]
"""``(gross commission, gross gateway) → discount`` — see ``promo_rules.discounter``."""


@dataclass(frozen=True)
class Charge:
    base_amount_minor: int
    commission_minor: int
    gateway_fee_minor: int
    commission_discount_minor: int
    gateway_discount_minor: int
    taxable_minor: int
    tax_minor: int

    @property
    def net_commission_minor(self) -> int:
        return self.commission_minor - self.commission_discount_minor

    @property
    def net_gateway_minor(self) -> int:
        return self.gateway_fee_minor - self.gateway_discount_minor

    @property
    def discount_minor(self) -> int:
        return self.commission_discount_minor + self.gateway_discount_minor

    @property
    def total_minor(self) -> int:
        return (
            self.base_amount_minor
            + self.net_commission_minor
            + self.net_gateway_minor
            + self.tax_minor
        )


def compute_charge(
    base_minor: int, rates: PricingRates, discount: Discounter | None = None
) -> Charge:
    if base_minor < 0:
        raise ValueError("base amount cannot be negative")
    commission = platform_fee(base_minor, rates.commission_pct)
    gateway = platform_fee(base_minor + commission, rates.gateway_pct)
    off = discount(commission, gateway) if discount else FeeDiscount()
    if not (0 <= off.commission_minor <= commission and 0 <= off.gateway_minor <= gateway):
        raise ValueError("discount must be between zero and the fee it reduces")
    taxable = taxable_amount(base_minor, commission - off.commission_minor, rates.tax_base)
    return Charge(
        base_amount_minor=base_minor,
        commission_minor=commission,
        gateway_fee_minor=gateway,
        commission_discount_minor=off.commission_minor,
        gateway_discount_minor=off.gateway_minor,
        taxable_minor=taxable,
        tax_minor=platform_fee(taxable, rates.tax_pct),
    )
