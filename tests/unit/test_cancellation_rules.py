"""Shift cancellation maths (rules §5, §6) on the shared pricing engine, with and without tax."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.services.cancellations.cancellation_rules import (
    EVENT_CANCEL,
    EVENT_UNFILLED,
    PARTY_BUSINESS,
    PARTY_SYSTEM,
    PARTY_WORKER,
    Policy,
    Tier,
    hours_before,
    pick_tier,
    quote_seat,
    quote_unfilled,
)
from app.services.promos.promo_rules import Promo
from app.utils.money import FeeRates

NOW = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
NO_TAX = FeeRates(Decimal(4), Decimal(4), Decimal(2))
TAXED = FeeRates(Decimal(4), Decimal(4), Decimal(2), Decimal(2), "subtotal", "Tax")


def _tier(party: str, hours_from: str, hours_to: str | None, **kw: object) -> Tier:
    values: dict = {
        "party": party,
        "event": EVENT_CANCEL,
        "hours_from": Decimal(hours_from),
        "hours_to": Decimal(hours_to) if hours_to else None,
        "flat_fee_minor": 0,
        "booking_pct": Decimal(0),
        "fee_cap_minor": None,
        "worker_share_pct": Decimal(0),
        "strike_weight": Decimal(0),
        "business_voucher": False,
    }
    values.update(kw)
    return Tier(**values)


POLICY = Policy(
    version=3,
    strike_window_days=30,
    strikes_to_limit=Decimal(3),
    limit_days=7,
    strikes_to_ban=Decimal(5),
    voucher_valid_days=30,
    tiers=(
        _tier(PARTY_BUSINESS, "0", "2", booking_pct=Decimal(50), worker_share_pct=Decimal(25)),
        _tier(PARTY_BUSINESS, "2", None),
        _tier(
            PARTY_WORKER,
            "0",
            "2",
            flat_fee_minor=5_000,
            fee_cap_minor=4_000,
            strike_weight=Decimal(1),
            business_voucher=True,
        ),
    ),
)


def _business_quote(rates: FeeRates, *, promo: Promo | None = None, hours: int = 1):  # type: ignore[no-untyped-def]
    return quote_seat(
        POLICY,
        party=PARTY_BUSINESS,
        event=EVENT_CANCEL,
        booking_minor=80_000,
        rates=rates,
        starts_at=NOW + timedelta(hours=hours),
        now=NOW,
        promo=promo,
    )


def test_hours_before_never_goes_negative() -> None:
    assert hours_before(NOW - timedelta(hours=1), NOW) == Decimal("0.00")
    assert hours_before(NOW + timedelta(minutes=90), NOW) == Decimal("1.50")


def test_pick_tier_uses_half_open_windows() -> None:
    assert pick_tier(POLICY, PARTY_BUSINESS, EVENT_CANCEL, Decimal("1.99")).hours_to == Decimal(2)
    assert pick_tier(POLICY, PARTY_BUSINESS, EVENT_CANCEL, Decimal(2)).hours_to is None
    assert pick_tier(POLICY, PARTY_SYSTEM, EVENT_CANCEL, Decimal(0)) is None


def test_late_business_cancel_without_tax_is_unchanged() -> None:
    quote = _business_quote(NO_TAX)
    # fee 50% of ₹800 = ₹400; commission kept 50% of ₹32 = ₹16; gateway ₹16.64 kept.
    assert quote.fee_minor == 40_000
    assert quote.business_retained_minor == 40_000 + 1_600 + 1_664
    assert quote.business_refund_minor == 84_864 - quote.business_retained_minor
    assert quote.worker_compensation_minor == 20_000


def test_late_business_cancel_keeps_tax_only_on_the_retained_share() -> None:
    quote = _business_quote(TAXED)
    # Seat tax 2% of ₹832 = ₹16.64; half of it is kept with the fee.
    assert quote.business_retained_minor == 40_000 + 1_600 + 1_664 + 832
    assert quote.business_refund_minor + quote.business_retained_minor == 84_864 + 1_664


def test_early_business_cancel_keeps_only_the_gateway_charge() -> None:
    quote = _business_quote(TAXED, hours=5)
    assert quote.fee_minor == 0
    assert quote.business_retained_minor == 1_664


def test_coupon_lowers_what_the_seat_cost_and_what_is_refunded() -> None:
    promo = Promo(uuid4(), "HALF", "percent", Decimal(50), "commission", None)
    with_coupon = _business_quote(NO_TAX, promo=promo, hours=5)
    without = _business_quote(NO_TAX, hours=5)
    assert without.business_refund_minor - with_coupon.business_refund_minor == 1_600


def test_zero_booking_keeps_no_commission() -> None:
    quote = quote_seat(
        POLICY,
        party=PARTY_BUSINESS,
        event=EVENT_CANCEL,
        booking_minor=0,
        rates=TAXED,
        starts_at=NOW + timedelta(hours=1),
        now=NOW,
    )
    assert quote.business_retained_minor == 0
    assert quote.business_refund_minor == 0


def test_worker_cancel_refunds_the_whole_seat_and_caps_the_fee() -> None:
    quote = quote_seat(
        POLICY,
        party=PARTY_WORKER,
        event=EVENT_CANCEL,
        booking_minor=80_000,
        rates=TAXED,
        starts_at=NOW + timedelta(hours=1),
        now=NOW,
    )
    assert quote.fee_minor == 4_000
    assert quote.business_refund_minor == 84_864 + 1_664
    assert quote.strike_weight == Decimal(1)
    assert quote.business_voucher is True


def test_worker_cancel_outside_any_tier_is_free() -> None:
    quote = quote_seat(
        POLICY,
        party=PARTY_WORKER,
        event=EVENT_CANCEL,
        booking_minor=80_000,
        rates=NO_TAX,
        starts_at=NOW + timedelta(hours=5),
        now=NOW,
    )
    assert (quote.fee_minor, quote.strike_weight, quote.business_voucher) == (0, 0, False)


def test_unfilled_seats_are_refunded_in_full_including_tax() -> None:
    quote = quote_unfilled(
        POLICY, booking_minor=80_000, seats=2, rates=TAXED, starts_at=NOW, now=NOW
    )
    assert quote.event == EVENT_UNFILLED
    assert quote.business_refund_minor == 2 * (84_864 + 1_664)
    assert quote.business_voucher is True
