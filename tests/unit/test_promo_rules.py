"""Coupon rules: eligibility reasons, booking types, minimums, fee discounts and caps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.pricing.pricing_engine import FeeDiscount, PricingRates, compute_charge
from app.services.promos.promo_rules import (
    BOOKING_LIVE,
    BOOKING_SHIFT,
    Promo,
    discounter,
    fee_discount,
    promo_problem,
    worker_commission_discount,
)

NOW = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
OWNER = uuid4()


def _row(**overrides: object) -> dict:
    row = {
        "id": uuid4(),
        "code": "SAVE10",
        "is_active": True,
        "target_role": "business",
        "owner_user_id": None,
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=1),
        "max_uses": 10,
        "used_count": 0,
        "max_uses_per_user": 1,
        "booking_types": "all",
        "min_booking_minor": None,
        "discount_type": "percent",
        "discount_value": Decimal(10),
        "applies_to": "commission",
        "max_discount_minor": None,
    }
    row.update(overrides)
    return row


def _problem(row: dict | None, **kwargs: object) -> str | None:
    args: dict = {"role": "business", "user_id": OWNER, "now": NOW, "user_uses": 0}
    args.update(kwargs)
    return promo_problem(row, **args)


def test_a_valid_coupon_has_no_problem() -> None:
    assert _problem(_row()) is None
    assert _problem(_row(), booking_type=BOOKING_LIVE, amount_minor=1) is None


@pytest.mark.parametrize(
    ("row", "kwargs", "reason"),
    [
        (None, {}, "not_found"),
        (_row(is_active=False), {}, "not_found"),
        (_row(target_role="worker"), {}, "wrong_role"),
        (_row(owner_user_id=uuid4()), {}, "not_found"),
        (_row(valid_from=NOW + timedelta(seconds=1)), {}, "not_started"),
        (_row(valid_until=NOW), {}, "expired"),
        (_row(max_uses=3, used_count=3), {}, "used_up"),
        (_row(), {"user_uses": 1}, "already_used"),
        (_row(booking_types=BOOKING_SHIFT), {"booking_type": BOOKING_LIVE}, "wrong_booking_type"),
        (_row(booking_types=BOOKING_LIVE), {"booking_type": BOOKING_SHIFT}, "wrong_booking_type"),
        (_row(min_booking_minor=50_000), {"amount_minor": 49_999}, "below_minimum"),
        (_row(applies_to="gateway"), {"booking_type": BOOKING_LIVE}, "not_applicable"),
    ],
)
def test_each_rejection_reason(row: dict | None, kwargs: dict, reason: str) -> None:
    assert _problem(row, **kwargs) == reason


def test_coupon_assigned_to_this_business_is_usable() -> None:
    assert _problem(_row(owner_user_id=OWNER)) is None


def test_no_end_date_and_unlimited_uses_are_allowed() -> None:
    assert _problem(_row(valid_until=None, max_uses=None, used_count=999)) is None


def test_minimum_is_inclusive_and_skipped_without_an_amount() -> None:
    assert _problem(_row(min_booking_minor=50_000), amount_minor=50_000) is None
    assert _problem(_row(min_booking_minor=50_000)) is None


def test_booking_type_is_not_checked_when_unknown() -> None:
    assert _problem(_row(booking_types=BOOKING_SHIFT)) is None


def _promo(**overrides: object) -> Promo:
    return Promo.from_row(_row(**overrides))


def test_percent_off_commission() -> None:
    assert fee_discount(_promo(), 4_000, 1_600) == FeeDiscount(commission_minor=400)


def test_percent_off_gateway() -> None:
    assert fee_discount(_promo(applies_to="gateway"), 4_000, 1_600) == FeeDiscount(
        gateway_minor=160
    )


def test_all_fees_comes_off_commission_first() -> None:
    promo = _promo(applies_to="all_fees", discount_type="flat", discount_value=Decimal(50))
    assert fee_discount(promo, 4_000, 1_600) == FeeDiscount(
        commission_minor=4_000, gateway_minor=1_000
    )


def test_flat_amount_is_in_rupees_and_shared_by_scale() -> None:
    promo = _promo(discount_type="flat", discount_value=Decimal(20))
    assert fee_discount(promo, 4_000, 0).commission_minor == 2_000
    assert fee_discount(promo, 4_000, 0, scale=Decimal("0.5")).commission_minor == 1_000


def test_waive_fees_removes_the_whole_fee() -> None:
    promo = _promo(discount_type="waive_fees", applies_to="all_fees", discount_value=Decimal(0))
    assert fee_discount(promo, 4_000, 1_600).total_minor == 5_600


def test_max_discount_caps_the_amount() -> None:
    promo = _promo(discount_value=Decimal(50), max_discount_minor=1_500)
    assert fee_discount(promo, 4_000, 0).commission_minor == 1_500


def test_discount_never_exceeds_the_fee() -> None:
    promo = _promo(discount_type="flat", discount_value=Decimal(1_000))
    assert fee_discount(promo, 4_000, 0).commission_minor == 4_000


def test_nothing_to_discount_gives_zero() -> None:
    assert fee_discount(_promo(applies_to="gateway"), 4_000, 0) == FeeDiscount()
    assert fee_discount(_promo(), 0, 0) == FeeDiscount()


def test_discounter_plugs_into_the_pricing_engine() -> None:
    rates = PricingRates(commission_pct=Decimal(4), tax_pct=Decimal(2))
    charge = compute_charge(100_000, rates, discounter(_promo()))
    assert charge.commission_discount_minor == 400
    assert charge.tax_minor == 2_072  # 2% of (₹1,000 + ₹36)
    assert discounter(None) is None


def test_worker_codes_discount_only_the_commission() -> None:
    assert worker_commission_discount(_promo(discount_value=Decimal(25)), 3_200) == 800
