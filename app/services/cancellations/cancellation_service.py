"""Applies cancellation rules: charge record, worker wallet fee / compensation, strikes and
free-fees vouchers. Callers own the transaction and the assignment / shift status change."""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.constants.billing.billing_route_strings import INVOICE_KIND_DEPOSIT, INVOICE_PAID
from app.constants.notifications.notification_route_strings import (
    KIND_CANCELLATION_COMPENSATION,
    KIND_CANCELLATION_FEE,
    KIND_STRIKE_ADDED,
    KIND_VOUCHER_ISSUED,
)
from app.repositories.billing import billing_repository
from app.repositories.cancellations import cancellation_repository
from app.repositories.profiles import profile_repository
from app.schemas.shifts.shift_schemas import CancellationQuote
from app.services.cancellations.cancellation_rules import (
    PARTY_BUSINESS,
    PARTY_WORKER,
    Policy,
    SeatQuote,
    Tier,
    quote_seat,
    quote_unfilled,
)
from app.services.catalog import catalog_service
from app.services.notifications.notification_service import notify
from app.services.promos import promo_service
from app.services.shifts.domain.shift_rules import shift_seat_pay
from app.utils.money import FeeRates

LEDGER_CANCELLATION_FEE = "cancellation_fee"
LEDGER_CANCELLATION_COMPENSATION = "cancellation_compensation"
LEDGER_ADJUSTMENT = "adjustment"
_VOUCHER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_NO_POLICY = Policy(
    version=0,
    strike_window_days=90,
    strikes_to_limit=Decimal(2),
    limit_days=7,
    strikes_to_ban=Decimal(3),
    voucher_valid_days=60,
    tiers=(),
)


def _rupees(minor: int) -> str:
    return f"₹{minor / 100:,.2f}".replace(".00", "")


async def load_policy(conn: asyncpg.Connection) -> Policy:
    row = await cancellation_repository.get_active_policy(conn)
    if row is None:
        return _NO_POLICY
    tiers = await cancellation_repository.list_policy_tiers(conn, row["version"])
    return Policy(**dict(row), tiers=tuple(Tier(**dict(t)) for t in tiers))


async def _rates(conn: asyncpg.Connection, shift: asyncpg.Record) -> FeeRates:
    return catalog_service.shift_rates(shift) or await catalog_service.active_rates(conn)


def seat_booking_minor(shift: asyncpg.Record, hourly_rate_minor: int) -> int:
    """Booked pay for one seat: rate × booked time, or the task price."""
    return shift_seat_pay(shift, hourly_rate_minor)


async def quote_assignment(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    hourly_rate_minor: int,
    *,
    party: str,
    event: str,
    now: datetime,
) -> SeatQuote:
    return quote_seat(
        await load_policy(conn),
        party=party,
        event=event,
        booking_minor=seat_booking_minor(shift, hourly_rate_minor),
        rates=await _rates(conn, shift),
        starts_at=shift["starts_at"],
        now=now,
        promo=await promo_service.shift_promo(conn, shift),
        seats=shift["workers_required"],
    )


def quote_view(quote: SeatQuote, currency: str, *, seat_reopens: bool) -> CancellationQuote:
    return CancellationQuote(
        party=quote.party,  # type: ignore[arg-type]
        event=quote.event,  # type: ignore[arg-type]
        hours_before=float(quote.hours_before),
        booking_minor=quote.booking_minor,
        fee_minor=quote.fee_minor,
        worker_compensation_minor=quote.worker_compensation_minor,
        business_refund_minor=0 if seat_reopens else quote.business_refund_minor,
        strike_weight=float(quote.strike_weight),
        business_voucher=quote.business_voucher,
        seat_reopens=seat_reopens,
        currency=currency,
    )


async def deposit_refundable(conn: asyncpg.Connection, shift_id: UUID) -> int:
    """Paid deposit minus what earlier cancellations already kept."""
    deposit = await billing_repository.get_invoice_by_shift(conn, shift_id, INVOICE_KIND_DEPOSIT)
    if deposit is None or deposit["status"] != INVOICE_PAID:
        return 0
    retained = await cancellation_repository.sum_retained(conn, shift_id)
    return max(deposit["total_minor"] - retained, 0)


async def issue_voucher(
    conn: asyncpg.Connection, shift: asyncpg.Record, policy: Policy, now: datetime
) -> UUID:
    business = await profile_repository.get_business_profile(conn, shift["business_profile_id"])
    code = "FREE" + "".join(secrets.choice(_VOUCHER_ALPHABET) for _ in range(6))
    voucher_id = await cancellation_repository.insert_voucher(
        conn,
        code=code,
        owner_user_id=business["user_id"],
        source_shift_id=shift["id"],
        valid_until=now + timedelta(days=policy.voucher_valid_days),
    )
    await notify(
        conn,
        business["user_id"],
        KIND_VOUCHER_ISSUED,
        "Free fees on your next shift",
        f"Use code {code} within {policy.voucher_valid_days} days ({shift['job_title']}).",
        {"shift_id": shift["id"], "promo_code": code},
    )
    return voucher_id


async def add_strike(
    conn: asyncpg.Connection,
    *,
    worker_profile_id: UUID,
    worker_user_id: UUID,
    assignment_id: UUID | None,
    weight: Decimal,
    reason: str,
    policy: Policy,
    now: datetime,
) -> None:
    await cancellation_repository.insert_strike(
        conn,
        worker_profile_id=worker_profile_id,
        assignment_id=assignment_id,
        weight=weight,
        reason=reason,
        expires_at=now + timedelta(days=policy.strike_window_days),
    )
    total = await cancellation_repository.active_strike_weight(conn, worker_profile_id, now)
    if total >= policy.strikes_to_ban:
        if await cancellation_repository.ban_worker(conn, worker_profile_id, now):
            body = "Your worker account is on hold. Contact support to review it."
        else:
            return
    elif total >= policy.strikes_to_limit:
        await cancellation_repository.limit_worker_feed(
            conn, worker_profile_id, now + timedelta(days=policy.limit_days)
        )
        body = f"You'll see fewer shifts for {policy.limit_days} days."
    else:
        body = f"{total.normalize()} strike(s) in the last {policy.strike_window_days} days."
    await notify(
        conn,
        worker_user_id,
        KIND_STRIKE_ADDED,
        f"Strike added ({weight.normalize()})",
        body,
        {"assignment_id": assignment_id, "strikes": float(total)},
    )


async def apply_seat(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    assignment_id: UUID,
    worker_profile_id: UUID,
    worker_user_id: UUID,
    quote: SeatQuote,
    actor_user_id: UUID | None,
    now: datetime,
    seat_reopens: bool = False,
) -> CancellationQuote:
    """Record one cancelled / no-show seat and move the money it causes."""
    policy = await load_policy(conn)
    if seat_reopens:
        quote = replace(quote, business_refund_minor=0)
    voucher_id = await issue_voucher(conn, shift, policy, now) if quote.business_voucher else None
    await cancellation_repository.insert_charge(
        conn,
        shift_id=shift["id"],
        assignment_id=assignment_id,
        party=quote.party,
        event=quote.event,
        policy_version=quote.policy_version or None,
        hours_before=quote.hours_before,
        seats=1,
        booking_minor=quote.booking_minor,
        fee_minor=quote.fee_minor,
        worker_compensation_minor=quote.worker_compensation_minor,
        business_refund_minor=quote.business_refund_minor,
        business_retained_minor=quote.business_retained_minor,
        strike_weight=quote.strike_weight,
        voucher_promo_id=voucher_id,
        currency=shift["currency"],
        actor_user_id=actor_user_id,
    )
    data = {"shift_id": shift["id"], "assignment_id": assignment_id}
    if quote.party == PARTY_WORKER and quote.fee_minor:
        await cancellation_repository.insert_worker_ledger(
            conn,
            worker_profile_id=worker_profile_id,
            entry_type=LEDGER_CANCELLATION_FEE,
            amount_minor=-quote.fee_minor,
            currency=shift["currency"],
            assignment_id=assignment_id,
            description=f"Cancellation fee: {shift['job_title']}",
        )
        await notify(
            conn,
            worker_user_id,
            KIND_CANCELLATION_FEE,
            f"Cancellation fee {_rupees(quote.fee_minor)}",
            f"{shift['job_title']}. It's deducted from your wallet.",
            data,
        )
    if quote.party == PARTY_BUSINESS and quote.worker_compensation_minor:
        await cancellation_repository.insert_worker_ledger(
            conn,
            worker_profile_id=worker_profile_id,
            entry_type=LEDGER_CANCELLATION_COMPENSATION,
            amount_minor=quote.worker_compensation_minor,
            currency=shift["currency"],
            assignment_id=assignment_id,
            description=f"Late cancellation by business: {shift['job_title']}",
        )
        await notify(
            conn,
            worker_user_id,
            KIND_CANCELLATION_COMPENSATION,
            f"You got {_rupees(quote.worker_compensation_minor)} compensation",
            f"The business cancelled {shift['job_title']} late.",
            data,
        )
    if quote.strike_weight:
        await add_strike(
            conn,
            worker_profile_id=worker_profile_id,
            worker_user_id=worker_user_id,
            assignment_id=assignment_id,
            weight=quote.strike_weight,
            reason=quote.event,
            policy=policy,
            now=now,
        )
    return quote_view(quote, shift["currency"], seat_reopens=seat_reopens)


async def release_unfilled(
    conn: asyncpg.Connection, shift: asyncpg.Record, unfilled: int, now: datetime
) -> CancellationQuote:
    """Seats nobody booked by the apply cut-off: refunded via the deposit, plus a voucher."""
    policy = await load_policy(conn)
    quote = quote_unfilled(
        policy,
        booking_minor=seat_booking_minor(shift, shift["hourly_rate_minor"]),
        seats=unfilled,
        rates=await _rates(conn, shift),
        starts_at=shift["starts_at"],
        now=now,
    )
    voucher_id = await issue_voucher(conn, shift, policy, now)
    await cancellation_repository.insert_charge(
        conn,
        shift_id=shift["id"],
        assignment_id=None,
        party=quote.party,
        event=quote.event,
        policy_version=quote.policy_version or None,
        hours_before=quote.hours_before,
        seats=unfilled,
        booking_minor=quote.booking_minor,
        fee_minor=0,
        worker_compensation_minor=0,
        business_refund_minor=quote.business_refund_minor,
        business_retained_minor=0,
        strike_weight=Decimal(0),
        voucher_promo_id=voucher_id,
        currency=shift["currency"],
        actor_user_id=None,
    )
    return quote_view(quote, shift["currency"], seat_reopens=False)
