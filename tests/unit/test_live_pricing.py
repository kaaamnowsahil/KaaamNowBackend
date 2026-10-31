"""Live Work pricing: defaults, tax bases, boundaries, rounding, extensions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.live_work.live_pricing import (
    TAX_BASE_BASE_AMOUNT,
    TAX_BASE_COMMISSION,
    TAX_BASE_SUBTOTAL,
    InvalidPercentage,
    LiveRates,
    booking_charge,
    charge_for_base,
    extension_charge,
    extension_rate,
    parse_percentage,
    validate_extension_minutes,
    validate_reserved_minutes,
    worked_charge,
)


def _rates(commission="4", tax="2", base=TAX_BASE_SUBTOTAL, surcharge="30") -> LiveRates:
    return LiveRates(
        version=1,
        commission_pct=Decimal(commission),
        tax_pct=Decimal(tax),
        tax_label="Tax",
        tax_base=base,
        extension_surcharge_pct=Decimal(surcharge),
    )


def test_default_booking_breakdown():
    # ₹500/h × 2 h = ₹1,000; 4% commission = ₹40; 2% tax on ₹1,040 = ₹20.80.
    charge = booking_charge(50_000, 120, _rates())
    assert charge.base_amount_minor == 100_000
    assert charge.commission_minor == 4_000
    assert charge.taxable_minor == 104_000
    assert charge.tax_minor == 2_080
    assert charge.total_minor == 106_080
    assert charge.worker_commission_minor == 4_000
    assert charge.worker_net_minor == 96_000


@pytest.mark.parametrize(
    ("tax_base", "taxable", "tax", "total"),
    [
        (TAX_BASE_SUBTOTAL, 104_000, 2_080, 106_080),
        (TAX_BASE_BASE_AMOUNT, 100_000, 2_000, 106_000),
        (TAX_BASE_COMMISSION, 4_000, 80, 104_080),
    ],
)
def test_tax_base_options(tax_base, taxable, tax, total):
    charge = booking_charge(50_000, 120, _rates(base=tax_base))
    assert (charge.taxable_minor, charge.tax_minor, charge.total_minor) == (taxable, tax, total)
    assert charge.commission_minor == 4_000  # commission never changes with the tax base


def test_zero_rates_charge_only_base():
    charge = booking_charge(50_000, 60, _rates(commission="0", tax="0"))
    assert charge.total_minor == charge.base_amount_minor == 50_000
    assert charge.worker_net_minor == 50_000


def test_hundred_percent_boundaries():
    charge = booking_charge(50_000, 60, _rates(commission="100", tax="100"))
    assert charge.commission_minor == 50_000
    assert charge.tax_minor == 100_000  # 100% of (base + commission)
    assert charge.worker_net_minor == 0


def test_rounding_is_half_up_per_component():
    # ₹333.33/h × 70 min = 38,888.5 → 38,889; 4% = 1,555.56 → 1,556; 2% of 40,445 = 808.9 → 809.
    charge = booking_charge(33_333, 70, _rates())
    assert charge.base_amount_minor == 38_889
    assert charge.commission_minor == 1_556
    assert charge.tax_minor == 809
    assert charge.total_minor == 38_889 + 1_556 + 809
    # Exactly half a paisa rounds up.
    assert (
        charge_for_base(
            25, commission_pct=Decimal(0), tax_pct=Decimal(2), tax_base=TAX_BASE_SUBTOTAL
        ).tax_minor
        == 1
    )


def test_fractional_percentages():
    charge = booking_charge(50_000, 60, _rates(commission="2.5", tax="1.25"))
    assert charge.commission_minor == 1_250
    assert charge.tax_minor == 641  # 1.25% of 51,250 = 640.625 → 641


def test_extension_uses_surcharge():
    assert extension_rate(50_000, Decimal(30)) == 65_000
    charge = extension_charge(
        50_000,
        30,
        surcharge_pct=Decimal(30),
        commission_pct=Decimal(4),
        tax_pct=Decimal(2),
        tax_base=TAX_BASE_SUBTOTAL,
    )
    assert charge.base_amount_minor == 32_500  # ₹650/h × 0.5 h
    assert charge.commission_minor == 1_300
    assert charge.tax_minor == 676
    assert charge.total_minor == 34_476
    assert charge.worker_net_minor == 31_200


def test_extension_with_zero_surcharge_matches_base_rate():
    charge = extension_charge(
        50_000,
        60,
        surcharge_pct=Decimal(0),
        commission_pct=Decimal(4),
        tax_pct=Decimal(2),
        tax_base=TAX_BASE_SUBTOTAL,
    )
    assert charge.base_amount_minor == 50_000


def test_worked_charge_is_pro_rata():
    charge = worked_charge(
        50_000, 45, commission_pct=Decimal(4), tax_pct=Decimal(2), tax_base=TAX_BASE_SUBTOTAL
    )
    assert charge.base_amount_minor == 37_500


@pytest.mark.parametrize("value", ["0", "4", "2.5", "100", 7, 0.5, "99.99"])
def test_parse_percentage_accepts(value):
    assert Decimal(0) <= parse_percentage(value) <= Decimal(100)


@pytest.mark.parametrize(
    "value", ["", "abc", "-1", "100.01", "101", "NaN", "Infinity", "1.234", None, True]
)
def test_parse_percentage_rejects(value):
    with pytest.raises(InvalidPercentage):
        parse_percentage(value)


def test_duration_validation():
    assert validate_reserved_minutes(120) is None
    assert validate_reserved_minutes(30) is not None
    assert validate_reserved_minutes(13 * 60) is not None
    assert validate_reserved_minutes(100) is not None
    assert validate_extension_minutes(30) is None
    assert validate_extension_minutes(15) is not None
    assert validate_extension_minutes(5 * 60) is not None


def test_coupon_comes_off_commission_before_tax_and_never_off_worker_pay():
    from uuid import uuid4

    from app.services.promos.promo_rules import Promo

    promo = Promo(uuid4(), "HALF", "percent", Decimal(50), "commission", None)
    charge = booking_charge(50_000, 120, _rates(), promo)
    assert charge.commission_minor == 4_000
    assert charge.discount_minor == 2_000
    assert charge.taxable_minor == 102_000
    assert charge.tax_minor == 2_040
    assert charge.total_minor == 100_000 + 2_000 + 2_040
    assert charge.worker_net_minor == 96_000


def test_coupon_is_worked_out_once_and_split_across_workers():
    from uuid import uuid4

    from app.services.promos.promo_rules import Promo

    flat = Promo(uuid4(), "FLAT50", "flat", Decimal(50), "commission", None)
    # Alone, ₹50 off is capped by one Worker's ₹40 commission.
    assert booking_charge(50_000, 120, _rates(), flat).discount_minor == 4_000
    # Three Workers: ₹50 once on ₹120 commission, split evenly (rounded down) per seat.
    seat = booking_charge(50_000, 120, _rates(), flat, workers=3)
    assert seat.discount_minor == 5_000 // 3
    assert seat.base_amount_minor == 100_000
    assert seat.worker_net_minor == 96_000

    capped = Promo(uuid4(), "HALFCAP", "percent", Decimal(50), "commission", 3_000)
    # 50% of ₹120 = ₹60, capped at ₹30 for the whole booking → ₹10 per Worker.
    assert booking_charge(50_000, 120, _rates(), capped, workers=3).discount_minor == 1_000
    assert booking_charge(50_000, 120, _rates(), workers=3) == booking_charge(50_000, 120, _rates())


def test_charge_without_coupon_has_no_discount():
    assert booking_charge(50_000, 120, _rates()).discount_minor == 0


def test_walk_off_keeps_a_pro_rata_share_of_the_booking_coupon():
    from app.services.live_work.live_pricing import prorated_discount

    assert prorated_discount(2_000, reserved_base_minor=100_000, base_minor=50_000) == 1_000
    assert prorated_discount(2_000, reserved_base_minor=100_000, base_minor=33_333) == 667
    assert prorated_discount(2_000, reserved_base_minor=100_000, base_minor=150_000) == 2_000
    assert prorated_discount(0, reserved_base_minor=100_000, base_minor=50_000) == 0
    assert prorated_discount(2_000, reserved_base_minor=0, base_minor=0) == 0


def test_flat_discount_is_capped_at_commission_and_taxed_after():
    charge = charge_for_base(
        10_000,
        commission_pct=Decimal(4),
        tax_pct=Decimal(2),
        tax_base="subtotal",
        discount_minor=1_000,
    )
    assert charge.commission_minor == 400
    assert charge.discount_minor == 400
    assert charge.taxable_minor == 10_000
    assert charge.tax_minor == 200
    assert charge.total_minor == 10_200


def test_completed_charge_discounts_the_booking_only_and_taxes_extensions():
    from app.services.live_work.live_pricing import LiveCharge, completed_charge

    booking = LiveCharge(100_000, 4_000, 102_000, 2_040, 4_000, discount_minor=2_000)
    extension = LiveCharge(50_000, 2_000, 52_000, 1_040, 2_000)
    charge = completed_charge(booking, [extension], Decimal(4))
    assert charge.discount_minor == 2_000
    assert charge.commission_minor == 6_000
    assert charge.taxable_minor == 154_000
    assert charge.tax_minor == 3_080
    assert charge.total_minor == 150_000 + 4_000 + 3_080
    assert charge.worker_net_minor == 144_000


def test_completed_charge_without_extensions_is_the_booking_charge():
    from app.services.live_work.live_pricing import LiveCharge, completed_charge

    booking = LiveCharge(100_000, 4_000, 104_000, 2_080, 4_000)
    assert completed_charge(booking, [], Decimal(4)) == booking
