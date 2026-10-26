"""Pure shift rules: time window, payable minutes, cost estimate, late cancellation."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.constants.shifts.shift_route_strings import (
    DASHBOARD_GROUP_COMPLETED,
    DASHBOARD_GROUP_EXPIRED,
    DASHBOARD_GROUP_IN_PROGRESS,
    DASHBOARD_GROUP_UPCOMING,
    DASHBOARD_UPCOMING_STATUSES,
    LIVE_START_TOLERANCE_MINUTES,
    MAX_SCHEDULE_AHEAD_DAYS,
    MAX_SHIFT_HOURS,
    MIN_SHIFT_MINUTES,
    MSG_BREAK_TOO_LONG,
    MSG_LIVE_START_NOW,
    MSG_SHIFT_IN_PAST,
    MSG_SHIFT_TOO_FAR,
    MSG_SHIFT_TOO_LONG,
    MSG_SHIFT_TOO_SHORT,
    MSG_SHIFT_TOO_SOON,
    MSG_SHIFT_WINDOW_INVALID,
    SHIFT_COMPLETED,
    SHIFT_IN_PROGRESS,
    SHIFT_LIVE,
)
from app.exceptions.api_errors import bad_request
from app.schemas.shifts.shift_schemas import ShiftCostEstimate
from app.services.promos.promo_rules import Promo, discount_charge
from app.utils.clock import minutes_between
from app.utils.money import FeeRates, business_charge, pay_for_minutes, worker_commission


def resolve_window(
    *,
    shift_type: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    duration_minutes: int | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Live shifts default to "now"; an end is given as ``ends_at`` or ``duration_minutes``."""
    if starts_at is None:
        if shift_type != SHIFT_LIVE:
            raise bad_request("starts_at_required", MSG_SHIFT_IN_PAST)
        starts_at = now
    if ends_at is None:
        if duration_minutes is None:
            raise bad_request("ends_at_required", MSG_SHIFT_WINDOW_INVALID)
        ends_at = starts_at + timedelta(minutes=duration_minutes)
    return starts_at, ends_at


def validate_window(
    *,
    shift_type: str,
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    now: datetime,
    min_lead_hours: int = 0,
) -> None:
    if ends_at <= starts_at:
        raise bad_request("shift_window_invalid", MSG_SHIFT_WINDOW_INVALID)
    length = minutes_between(starts_at, ends_at)
    if length < MIN_SHIFT_MINUTES:
        raise bad_request("shift_too_short", MSG_SHIFT_TOO_SHORT)
    if length > MAX_SHIFT_HOURS * 60:
        raise bad_request("shift_too_long", MSG_SHIFT_TOO_LONG)
    if break_minutes >= length:
        raise bad_request("break_too_long", MSG_BREAK_TOO_LONG)
    tolerance = timedelta(minutes=LIVE_START_TOLERANCE_MINUTES)
    if shift_type == SHIFT_LIVE:
        if abs(starts_at - now) > tolerance:
            raise bad_request("live_start_now", MSG_LIVE_START_NOW)
    else:
        if starts_at <= now:
            raise bad_request("shift_in_past", MSG_SHIFT_IN_PAST)
        if starts_at < now + timedelta(hours=min_lead_hours):
            raise bad_request("shift_too_soon", MSG_SHIFT_TOO_SOON.format(hours=min_lead_hours))
        if starts_at > now + timedelta(days=MAX_SCHEDULE_AHEAD_DAYS):
            raise bad_request("shift_too_far", MSG_SHIFT_TOO_FAR)


def paid_minutes(starts_at: datetime, ends_at: datetime, break_minutes: int) -> int:
    return max(minutes_between(starts_at, ends_at) - break_minutes, 0)


def estimate_cost(
    *,
    hourly_rate_minor: int,
    workers_required: int,
    minutes_per_worker: int,
    rates: FeeRates,
    currency: str,
    promo: Promo | None = None,
) -> ShiftCostEstimate:
    pay_per_worker = pay_for_minutes(hourly_rate_minor, minutes_per_worker)
    charge, discount = discount_charge(
        business_charge(pay_per_worker * workers_required, rates), promo
    )
    worker_fee = worker_commission(pay_per_worker, rates)
    return ShiftCostEstimate(
        currency=currency,
        paid_minutes_per_worker=minutes_per_worker,
        pay_per_worker_minor=pay_per_worker,
        workers_required=workers_required,
        worker_subtotal_minor=charge.worker_subtotal_minor,
        fee_percentage=float(rates.business_pct),
        platform_fee_minor=charge.commission_minor,
        gateway_fee_percentage=float(rates.gateway_pct),
        gateway_fee_minor=charge.gateway_fee_minor,
        total_minor=charge.total_minor,
        promo_code=promo.code if promo else None,
        promo_discount_minor=discount,
        worker_fee_percentage=float(rates.worker_pct),
        worker_fee_per_worker_minor=worker_fee,
        worker_net_per_worker_minor=pay_per_worker - worker_fee,
    )


def dashboard_group(status: str, ends_at: datetime, now: datetime) -> str:
    """Home section for a shift; recruiting/filled shifts past their end count as expired
    even before the sweep flips their status."""
    if status == SHIFT_COMPLETED:
        return DASHBOARD_GROUP_COMPLETED
    if status == SHIFT_IN_PROGRESS:
        return DASHBOARD_GROUP_IN_PROGRESS
    if status in DASHBOARD_UPCOMING_STATUSES and ends_at > now:
        return DASHBOARD_GROUP_UPCOMING
    return DASHBOARD_GROUP_EXPIRED


def is_late_cancellation(starts_at: datetime, cutoff_hours: int, now: datetime) -> bool:
    return now >= starts_at - timedelta(hours=cutoff_hours)
