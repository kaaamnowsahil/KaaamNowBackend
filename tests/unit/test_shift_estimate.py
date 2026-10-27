"""Shift "Estimated cost": the same breakdown the deposit invoice charges, tax included."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.services.promos.promo_rules import Promo
from app.services.shifts.domain.shift_rules import estimate_cost
from app.utils.money import FeeRates

TAXED = FeeRates(Decimal(4), Decimal(4), Decimal(2), Decimal(2), "subtotal", "Tax")


def test_estimate_shows_tax_separately_from_commission_and_gateway() -> None:
    # 2 workers × 4 h × ₹100/h = ₹800.
    estimate = estimate_cost(
        hourly_rate_minor=10_000,
        workers_required=2,
        minutes_per_worker=240,
        rates=TAXED,
        currency="INR",
    )
    assert estimate.worker_subtotal_minor == 80_000
    assert estimate.platform_fee_minor == 3_200
    assert estimate.gateway_fee_minor == 1_664
    assert estimate.tax_percentage == 2.0
    assert estimate.tax_label == "Tax"
    assert estimate.tax_base == "subtotal"
    assert estimate.taxable_minor == 83_200
    assert estimate.tax_minor == 1_664
    assert estimate.total_minor == 80_000 + 3_200 + 1_664 + 1_664
    assert estimate.worker_net_per_worker_minor == 40_000 - 1_600


def test_estimate_without_tax_has_zero_tax() -> None:
    estimate = estimate_cost(
        hourly_rate_minor=10_000,
        workers_required=1,
        minutes_per_worker=60,
        rates=FeeRates(Decimal(4), Decimal(4), Decimal(2)),
        currency="INR",
    )
    assert estimate.tax_minor == 0
    assert estimate.total_minor == 10_000 + 400 + 208


def test_coupon_discount_is_reported_and_lowers_the_tax() -> None:
    promo = Promo(uuid4(), "HALF", "percent", Decimal(50), "commission", None)
    estimate = estimate_cost(
        hourly_rate_minor=10_000,
        workers_required=2,
        minutes_per_worker=240,
        rates=TAXED,
        currency="INR",
        promo=promo,
    )
    assert estimate.promo_code == "HALF"
    assert estimate.promo_discount_minor == 1_600
    # Fees are shown gross with the coupon as its own line, so the lines add up to the total.
    assert estimate.platform_fee_minor == 3_200
    assert estimate.gateway_fee_minor == 1_664
    assert estimate.tax_minor == 1_632
    assert estimate.total_minor == 80_000 + 3_200 + 1_664 + 1_632 - 1_600
