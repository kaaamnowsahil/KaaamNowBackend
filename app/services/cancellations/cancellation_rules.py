"""Pure cancellation maths (marketplace rules §5, §6). No I/O, so previews and the real
cancel always agree."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.services.pricing.shift_pricing import as_business_charge, shift_charge
from app.services.promos.promo_rules import Promo
from app.utils.money import FeeRates, platform_fee, round_half_up

PARTY_WORKER = "worker"
PARTY_BUSINESS = "business"
PARTY_SYSTEM = "system"
EVENT_CANCEL = "cancel"
EVENT_NO_SHOW = "no_show"
EVENT_WALK_OFF = "walk_off"
EVENT_UNFILLED = "unfilled"


@dataclass(frozen=True)
class Tier:
    party: str
    event: str
    hours_from: Decimal
    hours_to: Decimal | None
    flat_fee_minor: int
    booking_pct: Decimal
    fee_cap_minor: int | None
    worker_share_pct: Decimal
    strike_weight: Decimal
    business_voucher: bool


@dataclass(frozen=True)
class Policy:
    version: int
    strike_window_days: int
    strikes_to_limit: Decimal
    limit_days: int
    strikes_to_ban: Decimal
    voucher_valid_days: int
    tiers: tuple[Tier, ...]


@dataclass(frozen=True)
class SeatQuote:
    """Money for one booked seat. ``business_retained_minor`` is kept from the deposit;
    ``business_refund_minor`` is the rest of that seat's deposit share."""

    party: str
    event: str
    hours_before: Decimal
    booking_minor: int
    fee_minor: int
    worker_compensation_minor: int
    business_refund_minor: int
    business_retained_minor: int
    strike_weight: Decimal
    business_voucher: bool
    policy_version: int


def hours_before(starts_at: datetime, now: datetime) -> Decimal:
    seconds = max((starts_at - now).total_seconds(), 0)
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))


def pick_tier(policy: Policy, party: str, event: str, hours: Decimal) -> Tier | None:
    for tier in policy.tiers:
        if tier.party != party or tier.event != event:
            continue
        if hours >= tier.hours_from and (tier.hours_to is None or hours < tier.hours_to):
            return tier
    return None


def _fee(tier: Tier | None, booking_minor: int) -> int:
    if tier is None:
        return 0
    fee = tier.flat_fee_minor + platform_fee(booking_minor, tier.booking_pct)
    return min(fee, tier.fee_cap_minor) if tier.fee_cap_minor is not None else fee


def quote_seat(
    policy: Policy,
    *,
    party: str,
    event: str,
    booking_minor: int,
    rates: FeeRates,
    starts_at: datetime,
    now: datetime,
    promo: Promo | None = None,
    seats: int = 1,
) -> SeatQuote:
    """Worker side: fee from the worker's wallet; the business gets the whole seat back.
    Business side: fee is a share of the booking; commission and tax on that share and the
    seat's gateway charge are kept; ``worker_share_pct`` of the booking goes to the worker."""
    hours = hours_before(starts_at, now)
    tier = pick_tier(policy, party, event, hours)
    fee = _fee(tier, booking_minor)
    seat = as_business_charge(
        shift_charge(booking_minor, rates, promo, scale=Decimal(1) / Decimal(max(seats, 1)))
    )
    if party == PARTY_BUSINESS:
        fee = min(fee, booking_minor)
        share = Decimal(fee) / booking_minor if booking_minor else Decimal(0)
        commission_kept = round_half_up(Decimal(seat.commission_minor) * share)
        tax_kept = round_half_up(Decimal(seat.tax_minor) * share)
        retained = fee + commission_kept + tax_kept + seat.gateway_fee_minor
        compensation = platform_fee(booking_minor, tier.worker_share_pct) if tier else 0
        return SeatQuote(
            party=party,
            event=event,
            hours_before=hours,
            booking_minor=booking_minor,
            fee_minor=fee,
            worker_compensation_minor=min(compensation, fee),
            business_refund_minor=seat.total_minor - retained,
            business_retained_minor=retained,
            strike_weight=Decimal(0),
            business_voucher=False,
            policy_version=policy.version,
        )
    return SeatQuote(
        party=party,
        event=event,
        hours_before=hours,
        booking_minor=booking_minor,
        fee_minor=fee,
        worker_compensation_minor=0,
        business_refund_minor=seat.total_minor,
        business_retained_minor=0,
        strike_weight=tier.strike_weight if tier else Decimal(0),
        business_voucher=tier.business_voucher if tier else False,
        policy_version=policy.version,
    )


def quote_unfilled(
    policy: Policy,
    *,
    booking_minor: int,
    seats: int,
    rates: FeeRates,
    starts_at: datetime,
    now: datetime,
) -> SeatQuote:
    """Seats still empty when applying closes: full refund for them plus a voucher."""
    return SeatQuote(
        party=PARTY_SYSTEM,
        event=EVENT_UNFILLED,
        hours_before=hours_before(starts_at, now),
        booking_minor=booking_minor * seats,
        fee_minor=0,
        worker_compensation_minor=0,
        business_refund_minor=shift_charge(booking_minor * seats, rates).total_minor,
        business_retained_minor=0,
        strike_weight=Decimal(0),
        business_voucher=True,
        policy_version=policy.version,
    )
