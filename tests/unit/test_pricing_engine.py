"""Shared pricing engine used by Shift and Live Work: commission, tax base, gateway, discounts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.pricing.pricing_engine import (
    DEFAULT_COMMISSION_PCT,
    DEFAULT_TAX_LABEL,
    DEFAULT_TAX_PCT,
    TAX_BASE_BASE_AMOUNT,
    TAX_BASE_COMMISSION,
    TAX_BASE_SUBTOTAL,
    FeeDiscount,
    InvalidPercentage,
    PricingRates,
    compute_charge,
    parse_percentage,
    taxable_amount,
)
from app.utils.money import FeeRates, business_charge


def _rates(commission="4", tax="2", base=TAX_BASE_SUBTOTAL, gateway="0") -> PricingRates:
    return PricingRates(
        commission_pct=Decimal(commission),
        tax_pct=Decimal(tax),
        tax_base=base,
        gateway_pct=Decimal(gateway),
    )


def test_defaults_are_four_and_two_percent() -> None:
    assert DEFAULT_COMMISSION_PCT == Decimal("4.00")
    assert DEFAULT_TAX_PCT == Decimal("2.00")
    assert DEFAULT_TAX_LABEL == "Tax"


def test_default_breakdown_taxes_base_plus_commission() -> None:
    # ₹1,000 work; 4% = ₹40; 2% of ₹1,040 = ₹20.80; total ₹1,060.80.
    charge = compute_charge(100_000, _rates())
    assert charge.base_amount_minor == 100_000
    assert charge.commission_minor == 4_000
    assert charge.gateway_fee_minor == 0
    assert charge.taxable_minor == 104_000
    assert charge.tax_minor == 2_080
    assert charge.discount_minor == 0
    assert charge.total_minor == 106_080


@pytest.mark.parametrize(
    ("tax_base", "taxable", "tax"),
    [
        (TAX_BASE_SUBTOTAL, 104_000, 2_080),
        (TAX_BASE_BASE_AMOUNT, 100_000, 2_000),
        (TAX_BASE_COMMISSION, 4_000, 80),
    ],
)
def test_each_tax_base(tax_base: str, taxable: int, tax: int) -> None:
    charge = compute_charge(100_000, _rates(base=tax_base))
    assert charge.taxable_minor == taxable
    assert charge.tax_minor == tax
    assert charge.total_minor == 104_000 + tax


def test_unknown_tax_base_is_rejected() -> None:
    with pytest.raises(ValueError, match="tax base"):
        taxable_amount(100, 4, "gross")


def test_amounts_round_half_up_to_whole_paise() -> None:
    # 4% of 12,345 = 493.8 → 494; 2% of 12,839 = 256.78 → 257.
    charge = compute_charge(12_345, _rates())
    assert (charge.commission_minor, charge.tax_minor) == (494, 257)
    # Exactly half a paisa rounds up: 2.5% of 100 = 2.5 → 3.
    assert compute_charge(100, _rates(commission="2.5", tax="0")).commission_minor == 3


def test_zero_rates_charge_only_the_work_amount() -> None:
    charge = compute_charge(55_500, _rates(commission="0", tax="0"))
    assert charge.total_minor == 55_500
    assert charge.tax_minor == charge.commission_minor == 0


def test_negative_base_is_rejected() -> None:
    with pytest.raises(ValueError, match="base"):
        compute_charge(-1, _rates())


def test_gateway_is_on_work_plus_commission_and_not_taxed() -> None:
    charge = compute_charge(80_000, _rates(tax="2", gateway="2"))
    assert charge.commission_minor == 3_200
    assert charge.gateway_fee_minor == 1_664  # 2% of ₹832
    assert charge.taxable_minor == 83_200
    assert charge.tax_minor == 1_664
    assert charge.total_minor == 80_000 + 3_200 + 1_664 + 1_664


@pytest.mark.parametrize("subtotal", [0, 1, 99, 12_345, 80_000, 999_999, 4_000_000])
def test_without_tax_it_matches_the_existing_shift_charge(subtotal: int) -> None:
    legacy = business_charge(subtotal, FeeRates(Decimal(4), Decimal(4), Decimal(2)))
    charge = compute_charge(subtotal, _rates(tax="0", gateway="2"))
    assert charge.commission_minor == legacy.commission_minor
    assert charge.gateway_fee_minor == legacy.gateway_fee_minor
    assert charge.total_minor == legacy.total_minor


def test_commission_discount_lowers_the_taxable_amount() -> None:
    charge = compute_charge(
        100_000, _rates(), discount=lambda commission, gateway: FeeDiscount(commission_minor=1_000)
    )
    assert charge.commission_discount_minor == 1_000
    assert charge.net_commission_minor == 3_000
    assert charge.taxable_minor == 103_000
    assert charge.tax_minor == 2_060
    assert charge.discount_minor == 1_000
    assert charge.total_minor == 100_000 + 3_000 + 2_060


def test_discount_on_base_amount_tax_does_not_change_tax() -> None:
    charge = compute_charge(
        100_000,
        _rates(base=TAX_BASE_BASE_AMOUNT),
        discount=lambda commission, gateway: FeeDiscount(commission_minor=commission),
    )
    assert charge.tax_minor == 2_000
    assert charge.total_minor == 102_000


def test_gateway_discount_comes_off_the_gateway_only() -> None:
    charge = compute_charge(
        80_000,
        _rates(tax="0", gateway="2"),
        discount=lambda commission, gateway: FeeDiscount(gateway_minor=gateway),
    )
    assert charge.net_gateway_minor == 0
    assert charge.net_commission_minor == 3_200
    assert charge.total_minor == 83_200


def test_discount_receives_gross_fees() -> None:
    seen: list[tuple[int, int]] = []

    def capture(commission: int, gateway: int) -> FeeDiscount:
        seen.append((commission, gateway))
        return FeeDiscount()

    compute_charge(80_000, _rates(gateway="2"), discount=capture)
    assert seen == [(3_200, 1_664)]


@pytest.mark.parametrize(
    "bad",
    [
        FeeDiscount(commission_minor=-1),
        FeeDiscount(gateway_minor=-1),
        FeeDiscount(commission_minor=4_001),
        FeeDiscount(gateway_minor=1),
    ],
)
def test_discount_can_never_exceed_the_fee_or_be_negative(bad: FeeDiscount) -> None:
    with pytest.raises(ValueError, match="discount"):
        compute_charge(100_000, _rates(), discount=lambda commission, gateway: bad)


def test_fee_discount_total() -> None:
    assert FeeDiscount(commission_minor=5, gateway_minor=7).total_minor == 12


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("4", "4.00"), (" 2.5 ", "2.50"), (0, "0.00"), (100, "100.00"), ("12.34", "12.34")],
)
def test_parse_percentage_accepts_valid_values(raw: object, expected: str) -> None:
    assert parse_percentage(raw) == Decimal(expected)


@pytest.mark.parametrize(
    "raw", [None, True, "", "abc", "NaN", "Infinity", "-0.01", "100.01", "1.234", object()]
)
def test_parse_percentage_rejects_invalid_values(raw: object) -> None:
    with pytest.raises(InvalidPercentage):
        parse_percentage(raw)
