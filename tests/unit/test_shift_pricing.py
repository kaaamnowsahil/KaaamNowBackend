"""Shift pricing on the shared engine: unchanged without tax, tax added when configured."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.pricing.shift_pricing import as_business_charge, pricing_rates, shift_charge
from app.services.promos.promo_rules import Promo
from app.utils.money import BusinessCharge, FeeRates

LEGACY = FeeRates(business_pct=Decimal(4), worker_pct=Decimal(4), gateway_pct=Decimal(2))
TAXED = FeeRates(
    business_pct=Decimal(4),
    worker_pct=Decimal(4),
    gateway_pct=Decimal(2),
    tax_pct=Decimal(2),
    tax_base="subtotal",
    tax_label="Tax",
)


def _promo(**overrides: object) -> Promo:
    values = {
        "id": uuid4(),
        "code": "SAVE",
        "discount_type": "percent",
        "discount_value": Decimal(50),
        "applies_to": "commission",
        "max_discount_minor": None,
    }
    values.update(overrides)
    return Promo(**values)  # type: ignore[arg-type]


def test_existing_shift_rates_have_no_tax() -> None:
    assert LEGACY.tax_pct == 0
    assert pricing_rates(LEGACY).tax_pct == 0
    assert pricing_rates(LEGACY).gateway_pct == Decimal(2)


def test_rules_example_is_unchanged_without_tax() -> None:
    # Marketplace rules §3: ₹800 pay, 4% = ₹32, ~2% gateway on ₹832 = ₹16.64.
    charge = shift_charge(80_000, LEGACY)
    assert (charge.commission_minor, charge.gateway_fee_minor, charge.tax_minor) == (
        3_200,
        1_664,
        0,
    )
    assert charge.total_minor == 84_864


def test_tax_is_added_on_pay_plus_commission() -> None:
    charge = shift_charge(80_000, TAXED)
    assert charge.taxable_minor == 83_200
    assert charge.tax_minor == 1_664
    assert charge.total_minor == 84_864 + 1_664


def test_commission_coupon_matches_the_previous_discount_maths() -> None:
    charge = shift_charge(80_000, LEGACY, _promo())
    assert charge.discount_minor == 1_600
    assert charge.total_minor == 84_864 - 1_600


def test_flat_coupon_is_shared_across_seats() -> None:
    promo = _promo(discount_type="flat", discount_value=Decimal(10))
    charge = shift_charge(80_000, LEGACY, promo, scale=Decimal(1) / Decimal(2))
    assert charge.discount_minor == 500


def test_business_charge_carries_net_fees_and_tax() -> None:
    business = as_business_charge(shift_charge(80_000, TAXED, _promo()))
    assert business == BusinessCharge(
        worker_subtotal_minor=80_000,
        commission_minor=1_600,
        gateway_fee_minor=1_664,
        tax_minor=1_632,  # 2% of (₹800 + ₹16 net commission)
    )
    assert business.total_minor == 80_000 + 1_600 + 1_664 + 1_632


def test_business_charge_without_tax_defaults_to_zero() -> None:
    assert BusinessCharge(100, 4, 2).total_minor == 106


@pytest.mark.parametrize("base", ["subtotal", "base_amount", "commission"])
def test_tax_base_is_passed_through(base: str) -> None:
    rates = FeeRates(Decimal(4), Decimal(4), Decimal(0), Decimal(2), base, "Tax")
    assert pricing_rates(rates).tax_base == base
