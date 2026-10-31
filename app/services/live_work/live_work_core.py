"""Live Work state transitions shared by Business, Worker, payment hooks and sweeps.

Cancellation money follows docs/marketplace-rules.md through the active cancellation policy
tiers (admin-configurable). A Live Work booking starts as soon as a Worker accepts, so the
"time before start" is 0 and the "less than 2 hours" tiers apply:

* Business, no Worker yet          → free; full refund (rules §6).
* Business, Worker assigned        → business cancel tier on the base amount; commission and tax
                                     are kept only on that fee; the Worker share is credited (§6).
* Worker, before starting          → worker cancel tier (fee, strike, Business voucher); the
                                     Business keeps its booking and the search restarts (§5).

Once the Worker has started (arrival code), the work ends one of three ways (rules §12):

* Completed with the Business's code → hourly: worked time is billed (up to the reserved +
                                     paid extra time) and the rest refunded; task: full price.
* Worker force-cancels             → the Worker is not paid; the Business is refunded in full
                                     and gets a free-fees voucher; strike per the walk-off tier.
* Business force-cancels           → the Business pays 100% (reserved + paid extra time, or the
                                     task price); the Worker gets ``business_stop_worker_share_pct``
                                     of the pay, the rest stays with the platform.

Several Workers: the price snapshot is per seat and every money rule above applies per seat
against that seat's own ledger (``seat_paid``: its share of the deposit + its paid extensions).
Seats nobody took when the search ends are refunded; the booking completes after its last seat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.billing.billing_route_strings import INVOICE_KIND_DEPOSIT
from app.constants.notifications.notification_route_strings import (
    KIND_EXTENSION_ANSWERED,
    KIND_SHIFT_CANCELLED,
    KIND_SHIFT_ENDED,
    KIND_WORKER_CHECKED_OUT,
)
from app.constants.shifts.shift_route_strings import (
    ASG_APPROVED,
    ASG_CHECKED_IN,
    ASG_CHECKED_OUT,
    ASG_CONFIRMED,
    ASG_EN_ROUTE,
    END_BUSINESS_STOPPED,
    END_COMPLETED,
    END_SCHEDULED,
    END_WORKER_LEFT,
    PRICING_TASK,
    SHIFT_COMPLETED,
    SHIFT_FILLED,
    SHIFT_IN_PROGRESS,
    SHIFT_SEARCHING,
)
from app.exceptions.api_errors import ApiError, conflict, not_found
from app.repositories.attendance import attendance_repository
from app.repositories.cancellations import cancellation_repository
from app.repositories.live_work import live_work_repository
from app.repositories.profiles import profile_repository
from app.repositories.shifts import assignment_repository, dispatch_repository, shift_repository
from app.services.attendance import completion_codes
from app.services.cancellations import cancellation_service
from app.services.cancellations.cancellation_rules import (
    EVENT_CANCEL,
    EVENT_WALK_OFF,
    PARTY_BUSINESS,
    PARTY_WORKER,
    SeatQuote,
    Tier,
    pick_tier,
)
from app.services.cancellations.cancellation_service import LEDGER_ADJUSTMENT
from app.services.catalog import catalog_service
from app.services.live_work import live_refund_service, live_work_billing
from app.services.live_work.live_pricing import (
    LiveCharge,
    charge_for_base,
    completed_charge,
    extension_base,
    prorated_discount,
)
from app.services.notifications.notification_service import notify
from app.utils.clock import minutes_between
from app.utils.money import pay_for_minutes, platform_fee

MSG_NOT_FOUND = "Live Work booking not found."
MSG_STATE = "This action isn't available at the current stage of the booking."


def not_found_error() -> ApiError:
    return not_found("live_work_not_found", MSG_NOT_FOUND)


def state_error(details: dict | None = None) -> ApiError:
    return conflict("live_work_state", MSG_STATE, details)


def tier_fee(tier: Tier | None, booking_minor: int) -> int:
    if tier is None:
        return 0
    fee = tier.flat_fee_minor + platform_fee(booking_minor, tier.booking_pct)
    return min(fee, tier.fee_cap_minor) if tier.fee_cap_minor is not None else fee


def _charge(pricing: asyncpg.Record, base_minor: int, *, with_coupon: bool = False) -> LiveCharge:
    """Charge on part of the booking. ``with_coupon`` keeps a pro-rata share of its coupon."""
    discount = (
        prorated_discount(
            pricing["promo_discount_minor"],
            reserved_base_minor=pricing["base_amount_minor"],
            base_minor=base_minor,
        )
        if with_coupon
        else 0
    )
    return charge_for_base(
        base_minor,
        commission_pct=Decimal(pricing["commission_pct"]),
        tax_pct=Decimal(pricing["tax_pct"]),
        tax_base=pricing["tax_base"],
        discount_minor=discount,
    )


ACTIVE_SEAT_STATUSES = (ASG_CONFIRMED, ASG_EN_ROUTE, ASG_CHECKED_IN)
BEFORE_START_SEAT_STATUSES = (ASG_CONFIRMED, ASG_EN_ROUTE)
DONE_SEAT_STATUSES = (ASG_CHECKED_OUT, ASG_APPROVED)


async def unrefunded_total(conn: asyncpg.Connection, shift_id: UUID) -> int:
    """Everything paid on the booking (deposit + extensions) minus what was already refunded."""
    paid = await live_work_billing.paid_invoices(conn, shift_id)
    paid_ids = {i["id"] for i in paid}
    refunded = sum(
        r["amount_minor"]
        for r in await live_work_repository.list_refunds(conn, shift_id)
        if r["invoice_id"] in paid_ids
    )
    return max(sum(i["total_minor"] for i in paid) - refunded, 0)


async def seat_paid(conn: asyncpg.Connection, pricing: asyncpg.Record, assignment_id: UUID) -> int:
    """One seat's ledger: its share of the paid deposit + its own paid extensions."""
    deposit, extensions = await live_work_billing.seat_invoices(
        conn, pricing["shift_id"], assignment_id
    )
    share = pricing["total_minor"] if deposit is not None else 0
    return share + sum(i["total_minor"] for i in extensions)


@dataclass(frozen=True)
class CancelPlan:
    party: str
    stage: str
    quote: SeatQuote | None
    refund_minor: int
    rule: str
    effect: str
    seats: tuple[tuple[asyncpg.Record, SeatQuote], ...] = ()
    empty_seat_refund_minor: int = 0


async def _business_seat_quote(
    conn: asyncpg.Connection, pricing: asyncpg.Record, assignment: asyncpg.Record
) -> SeatQuote:
    """Business releases a Worker before the arrival code is entered: free, full refund."""
    policy = await cancellation_service.load_policy(conn)
    paid = await seat_paid(conn, pricing, assignment["id"])
    return SeatQuote(
        party=PARTY_BUSINESS,
        event=EVENT_CANCEL,
        hours_before=Decimal(0),
        booking_minor=pricing["base_amount_minor"],
        fee_minor=0,
        worker_compensation_minor=0,
        business_refund_minor=paid,
        business_retained_minor=0,
        strike_weight=Decimal(0),
        business_voucher=False,
        policy_version=policy.version,
    )


async def _business_stop_quote(
    conn: asyncpg.Connection, pricing: asyncpg.Record, assignment: asyncpg.Record
) -> SeatQuote:
    """Business force-cancels a Worker who already started: 100% billed, Worker share paid."""
    policy = await cancellation_service.load_policy(conn)
    charge, _ = await _full_charge(conn, pricing["shift_id"], pricing, assignment["id"])
    paid = await seat_paid(conn, pricing, assignment["id"])
    return SeatQuote(
        party=PARTY_BUSINESS,
        event=EVENT_CANCEL,
        hours_before=Decimal(0),
        booking_minor=charge.base_amount_minor,
        fee_minor=charge.base_amount_minor,
        worker_compensation_minor=stop_worker_share(charge.base_amount_minor),
        business_refund_minor=max(paid - charge.total_minor, 0),
        business_retained_minor=min(charge.total_minor, paid),
        strike_weight=Decimal(0),
        business_voucher=False,
        policy_version=policy.version,
    )


def _sum_quotes(quotes: list[SeatQuote], empty_refund: int, policy_version: int) -> SeatQuote:
    return SeatQuote(
        party=PARTY_BUSINESS,
        event=EVENT_CANCEL,
        hours_before=Decimal(0),
        booking_minor=sum(q.booking_minor for q in quotes),
        fee_minor=sum(q.fee_minor for q in quotes),
        worker_compensation_minor=sum(q.worker_compensation_minor for q in quotes),
        business_refund_minor=sum(q.business_refund_minor for q in quotes) + empty_refund,
        business_retained_minor=sum(q.business_retained_minor for q in quotes),
        strike_weight=Decimal(0),
        business_voucher=False,
        policy_version=policy_version,
    )


_RULE_BEFORE_START = (
    "Rules §12: the Worker has not entered the arrival code yet — free cancellation, full refund."
)
_RULE_DURING_WORK = (
    "Rules §12: Business force-cancels after the Worker started — the Business pays 100%; "
    "the Worker gets their share of the pay."
)


async def business_cancel_plan(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment: asyncpg.Record | None = None,
) -> CancelPlan:
    """Cancel the whole booking: every Worker not started yet pays the business cancel tier on
    its own ledger, every Worker already working is force-cancelled (100% billed); seats
    nobody took are refunded in full."""
    status = shift["status"]
    if status == "awaiting_payment":
        return CancelPlan(
            PARTY_BUSINESS,
            "before_payment",
            None,
            0,
            "Not paid yet — no charge.",
            "The booking is cancelled. Nothing was charged.",
        )
    seats = await live_work_repository.list_assignments(conn, shift["id"])
    active = [a for a in seats if a["status"] in ACTIVE_SEAT_STATUSES]
    taken = sum(1 for a in seats if a["status"] != "cancelled")
    if status == SHIFT_SEARCHING and not taken:
        return CancelPlan(
            PARTY_BUSINESS,
            "before_acceptance",
            None,
            await unrefunded_total(conn, shift["id"]),
            "Rules §6: no Worker assigned yet — free cancellation, full refund.",
            "The search stops and the full amount is refunded to your payment method.",
        )
    empty_refund = max(shift["workers_required"] - taken, 0) * pricing["total_minor"]
    if status not in (SHIFT_SEARCHING, SHIFT_FILLED, SHIFT_IN_PROGRESS) or not (
        active or empty_refund
    ):
        raise state_error({"stage": status})
    quotes = [
        (
            a,
            await (
                _business_stop_quote(conn, pricing, a)
                if a["status"] == ASG_CHECKED_IN
                else _business_seat_quote(conn, pricing, a)
            ),
        )
        for a in active
    ]
    working = any(a["status"] == ASG_CHECKED_IN for a in active)
    policy = await cancellation_service.load_policy(conn)
    total = _sum_quotes([q for _, q in quotes], empty_refund, policy.version)
    return CancelPlan(
        PARTY_BUSINESS,
        "during_work" if working else "before_start",
        total,
        total.business_refund_minor,
        _RULE_DURING_WORK if working else _RULE_BEFORE_START,
        "Workers who already started are paid their share; the others are released and the "
        "rest of your payment is refunded."
        if working
        else "The Workers are released and your payment is refunded in full.",
        seats=tuple(quotes),
        empty_seat_refund_minor=empty_refund,
    )


async def business_seat_cancel_plan(
    conn: asyncpg.Connection, pricing: asyncpg.Record, assignment: asyncpg.Record
) -> CancelPlan:
    """Release one Worker: before they start, the business cancel tier on that seat only;
    once they started, a force-cancel (100% billed, Worker share paid)."""
    if assignment["status"] == ASG_CHECKED_IN:
        quote = await _business_stop_quote(conn, pricing, assignment)
        return CancelPlan(
            PARTY_BUSINESS,
            "during_work",
            quote,
            quote.business_refund_minor,
            _RULE_DURING_WORK,
            "The work stops now. You pay the full amount and the Worker gets their share.",
            seats=((assignment, quote),),
        )
    if assignment["status"] not in BEFORE_START_SEAT_STATUSES:
        raise state_error({"stage": assignment["status"]})
    quote = await _business_seat_quote(conn, pricing, assignment)
    return CancelPlan(
        PARTY_BUSINESS,
        "before_start",
        quote,
        quote.business_refund_minor,
        _RULE_BEFORE_START,
        "This Worker is released and that Worker's payment is refunded in full.",
        seats=((assignment, quote),),
    )


def _is_task(pricing: asyncpg.Record) -> bool:
    return pricing["pricing_mode"] == PRICING_TASK


def _hourly_base(pricing: asyncpg.Record, minutes: int) -> int:
    """Pay for ``minutes`` of work: reserved minutes at the rate, paid extra time with the
    extension surcharge."""
    reserved = pricing["reserved_minutes"]
    regular = min(minutes, reserved)
    extra = max(minutes - reserved, 0)
    return pay_for_minutes(pricing["hourly_rate_minor"], regular) + extension_base(
        pricing["hourly_rate_minor"], extra, Decimal(pricing["extension_surcharge_pct"])
    )


def worked_minutes(pricing: asyncpg.Record, assignment: asyncpg.Record, now: datetime) -> int:
    """Time worked so far, capped at the reserved + paid extra time."""
    cap = pricing["reserved_minutes"] + assignment["extended_minutes"]
    return min(minutes_between(assignment["checked_in_at"], now), cap)


async def _full_charge(
    conn: asyncpg.Connection, shift_id: UUID, pricing: asyncpg.Record, assignment_id: UUID
) -> tuple[LiveCharge, int]:
    """100% of one seat: the booking snapshot plus its applied extensions → (charge, extra min)."""
    applied = [
        e
        for e in await live_work_repository.list_extensions(conn, shift_id)
        if e["status"] == "applied" and e["assignment_id"] == assignment_id
    ]
    charge = completed_charge(
        live_work_billing.snapshot_charge(pricing),
        [live_work_billing.extension_snapshot_charge(e) for e in applied],
        Decimal(pricing["commission_pct"]),
    )
    return charge, sum(e["extra_minutes"] for e in applied)


def stop_worker_share(base_minor: int) -> int:
    """Business force-cancel during work: what the Worker keeps of the pay (before the
    platform charge, which is already taken from it)."""
    return platform_fee(base_minor, Decimal(load_settings().business_stop_worker_share_pct))


PLATFORM_SHARE_PREFIX = "Platform share"


async def worker_cancel_plan(
    conn: asyncpg.Connection, pricing: asyncpg.Record, assignment: asyncpg.Record, now: datetime
) -> tuple[CancelPlan, int]:
    """→ (plan, worked_minutes)."""
    policy = await cancellation_service.load_policy(conn)
    base = pricing["base_amount_minor"]
    if assignment["status"] in ("confirmed", "en_route"):
        tier = pick_tier(policy, PARTY_WORKER, EVENT_CANCEL, Decimal(0))
        quote = SeatQuote(
            party=PARTY_WORKER,
            event=EVENT_CANCEL,
            hours_before=Decimal(0),
            booking_minor=base,
            fee_minor=tier_fee(tier, base),
            worker_compensation_minor=0,
            business_refund_minor=0,
            business_retained_minor=0,
            strike_weight=tier.strike_weight if tier else Decimal(0),
            business_voucher=tier.business_voucher if tier else False,
            policy_version=policy.version,
        )
        return (
            CancelPlan(
                PARTY_WORKER,
                "before_start",
                quote,
                0,
                "Rules §5: Worker cancels less than 2 hours before start.",
                "The Business keeps its booking and we look for another Worker.",
            ),
            0,
        )
    if assignment["status"] != ASG_CHECKED_IN:
        raise state_error({"stage": assignment["status"]})
    paid = await seat_paid(conn, pricing, assignment["id"])
    tier = pick_tier(policy, PARTY_WORKER, EVENT_WALK_OFF, Decimal(0))
    quote = SeatQuote(
        party=PARTY_WORKER,
        event=EVENT_WALK_OFF,
        hours_before=Decimal(0),
        booking_minor=base,
        fee_minor=0,
        worker_compensation_minor=0,
        business_refund_minor=paid,
        business_retained_minor=0,
        strike_weight=tier.strike_weight if tier else Decimal(0),
        business_voucher=True,
        policy_version=policy.version,
    )
    return (
        CancelPlan(
            PARTY_WORKER,
            "during_work",
            quote,
            paid,
            "Rules §12: Worker force-cancels after starting — the Worker is not paid; the "
            "Business is refunded in full and gets a free-fees voucher for its next booking.",
            "You won't be paid for this work. The Business gets its money back.",
        ),
        worked_minutes(pricing, assignment, now),
    )


async def queue_split_refund(
    conn: asyncpg.Connection,
    shift_id: UUID,
    amount_minor: int,
    reason: str,
    actor_user_id: UUID | None,
    *,
    assignment_id: UUID | None = None,
    deposit_only: bool = False,
    scope: str | None = None,
) -> list[UUID | None]:
    """Refund ``amount_minor`` across paid invoices, newest payment first. A seat refund
    (``assignment_id``) uses that seat's extensions, then the shared deposit; ``deposit_only``
    (seats nobody took) uses the deposit alone."""
    if assignment_id is not None:
        deposit, extensions = await live_work_billing.seat_invoices(conn, shift_id, assignment_id)
        invoices = [*extensions, *([deposit] if deposit else [])]
    else:
        invoices = await live_work_billing.paid_invoices(conn, shift_id)
        if deposit_only:
            invoices = [i for i in invoices if i["invoice_kind"] == INVOICE_KIND_DEPOSIT]
    ids: list[UUID | None] = []
    remaining = amount_minor
    for invoice in invoices:
        if remaining <= 0:
            break
        part = min(remaining, invoice["total_minor"])
        refund_id = await live_refund_service.queue_refund(
            conn,
            shift_id=shift_id,
            invoice_id=invoice["id"],
            amount_minor=part,
            reason=reason,
            actor_user_id=actor_user_id,
            assignment_id=assignment_id,
            scope=scope,
        )
        ids.append(refund_id)
        remaining -= (
            await live_work_repository.refund_amount(conn, refund_id)
            if refund_id is not None
            else part
        )
    return ids


async def close_open_extensions(
    conn: asyncpg.Connection, shift_id: UUID, now: datetime, assignment_id: UUID | None = None
) -> None:
    for ext in await live_work_repository.list_extensions(conn, shift_id):
        if assignment_id is not None and ext["assignment_id"] != assignment_id:
            continue
        if ext["status"] in ("requested", "awaiting_payment"):
            await live_work_repository.set_extension_status(conn, ext["id"], "expired", now)
            if ext["invoice_id"]:
                await live_work_billing.void_invoice(conn, ext["invoice_id"])


def _duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


async def complete_booking(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment: asyncpg.Record,
    ended_by: str,
    actor_user_id: UUID | None,
    now: datetime,
) -> list[UUID | None]:
    """Complete Work for one seat (the Business's code, or the time ran out): hourly bills the
    time worked, up to the reserved + paid extra time, and refunds the rest; a task bills its
    fixed price. Credits the Worker. The booking completes after its last seat."""
    if assignment["status"] != ASG_CHECKED_IN:
        raise state_error({"stage": assignment["status"]})
    task = _is_task(pricing)
    await completion_codes.mark_used(conn, assignment["id"], now)
    await close_open_extensions(conn, shift["id"], now, assignment["id"])
    full, ext_minutes = await _full_charge(conn, shift["id"], pricing, assignment["id"])
    recorded = minutes_between(assignment["checked_in_at"], now)
    booked = pricing["reserved_minutes"] + ext_minutes
    worked = min(recorded, booked)
    if task or worked >= booked:
        charge = full
    else:
        charge = _charge(pricing, _hourly_base(pricing, worked), with_coupon=True)
    billed_minutes = recorded if task else worked
    await attendance_repository.set_check_out(
        conn,
        assignment["id"],
        now=now,
        latitude=None,
        longitude=None,
        note=f"Live Work completed by {ended_by}",
        recorded_minutes=recorded,
    )
    await attendance_repository.approve(
        conn,
        assignment["id"],
        approved_minutes=billed_minutes,
        note="Live Work: task completed" if task else "Live Work: worked time billed",
        now=now,
        approver_user_id=actor_user_id or assignment["worker_user_id"],
    )
    await assignment_repository.set_ended(
        conn, assignment["id"], END_COMPLETED if task else END_SCHEDULED
    )
    await live_work_repository.set_assignment_approved(conn, assignment["id"])
    description = (
        "Task completed (fixed price)"
        if task
        else f"Worked {_duration(worked)} of {_duration(booked)}"
    )
    paid = await seat_paid(conn, pricing, assignment["id"])
    await live_work_billing.create_final_invoice(
        conn,
        pricing,
        assignment_id=assignment["id"],
        charge=charge,
        description=description,
        minutes=billed_minutes,
        paid_minor=paid,
        now=now,
    )
    refund_ids = await queue_split_refund(
        conn,
        shift["id"],
        max(paid - charge.total_minor, 0),
        live_refund_service.REASON_UNWORKED_TIME,
        actor_user_id,
        assignment_id=assignment["id"],
    )
    await settle_status(conn, shift["id"], now, actor_user_id, f"live_work_completed_by_{ended_by}")
    data = {"shift_id": shift["id"], "assignment_id": assignment["id"], "live_work": True}
    await notify(
        conn,
        await business_user_id(conn, shift),
        KIND_WORKER_CHECKED_OUT,
        "Work completed",
        f"{shift['job_title']} · final bill ready",
        data,
    )
    await notify(
        conn,
        assignment["worker_user_id"],
        KIND_SHIFT_ENDED,
        "Work completed",
        f"{shift['job_title']} · earnings credited",
        data,
    )
    return refund_ids


async def _close_working_seat(
    conn: asyncpg.Connection,
    assignment: asyncpg.Record,
    *,
    approved_minutes: int,
    note: str,
    ended_reason: str,
    actor_user_id: UUID | None,
    now: datetime,
) -> None:
    await completion_codes.mark_used(conn, assignment["id"], now)
    await close_open_extensions(conn, assignment["shift_id"], now, assignment["id"])
    await attendance_repository.set_check_out(
        conn,
        assignment["id"],
        now=now,
        latitude=None,
        longitude=None,
        note=note,
        recorded_minutes=minutes_between(assignment["checked_in_at"], now),
    )
    await attendance_repository.approve(
        conn,
        assignment["id"],
        approved_minutes=approved_minutes,
        note=note,
        now=now,
        approver_user_id=actor_user_id or assignment["worker_user_id"],
    )
    await assignment_repository.set_ended(conn, assignment["id"], ended_reason)
    await live_work_repository.set_assignment_approved(conn, assignment["id"])


async def worker_walk_off(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment: asyncpg.Record,
    plan: CancelPlan,
    worked: int,
    actor_user_id: UUID,
    now: datetime,
) -> list[UUID | None]:
    """Worker force-cancels after starting: not paid; the Business gets everything back."""
    paid = await seat_paid(conn, pricing, assignment["id"])
    await _close_working_seat(
        conn,
        assignment,
        approved_minutes=0,
        note="Live Work: Worker force-cancelled, not paid",
        ended_reason=END_WORKER_LEFT,
        actor_user_id=actor_user_id,
        now=now,
    )
    await cancellation_service.apply_seat(
        conn,
        shift=shift,
        assignment_id=assignment["id"],
        worker_profile_id=assignment["worker_profile_id"],
        worker_user_id=assignment["worker_user_id"],
        quote=plan.quote,  # type: ignore[arg-type]
        actor_user_id=actor_user_id,
        now=now,
    )
    await live_work_billing.create_final_invoice(
        conn,
        pricing,
        assignment_id=assignment["id"],
        charge=_charge(pricing, 0),
        description=f"Not paid: the Worker cancelled after {_duration(worked)}",
        minutes=0,
        paid_minor=paid,
        now=now,
    )
    await settle_status(conn, shift["id"], now, actor_user_id, "live_work_worker_left")
    refund_ids = await queue_split_refund(
        conn,
        shift["id"],
        paid,
        live_refund_service.REASON_WORKER_LEFT,
        actor_user_id,
        assignment_id=assignment["id"],
    )
    await notify(
        conn,
        await business_user_id(conn, shift),
        KIND_SHIFT_ENDED,
        "The Worker cancelled the work",
        f"{shift['job_title']} · you get a full refund and no platform charge on your next "
        "booking.",
        {"shift_id": shift["id"], "assignment_id": assignment["id"], "live_work": True},
    )
    return refund_ids


async def business_force_stop(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment: asyncpg.Record,
    actor_user_id: UUID,
    now: datetime,
) -> list[UUID | None]:
    """Business force-cancels a Worker who already started: the Business pays 100% (reserved +
    paid extra time, or the task price); the Worker keeps their share, the rest stays with the
    platform."""
    task = _is_task(pricing)
    charge, ext_minutes = await _full_charge(conn, shift["id"], pricing, assignment["id"])
    booked = pricing["reserved_minutes"] + ext_minutes
    await _close_working_seat(
        conn,
        assignment,
        approved_minutes=minutes_between(assignment["checked_in_at"], now) if task else booked,
        note="Live Work: the Business force-cancelled during work",
        ended_reason=END_BUSINESS_STOPPED,
        actor_user_id=actor_user_id,
        now=now,
    )
    paid = await seat_paid(conn, pricing, assignment["id"])
    await live_work_billing.create_final_invoice(
        conn,
        pricing,
        assignment_id=assignment["id"],
        charge=charge,
        description=(
            "Task (fixed price): work stopped by the Business"
            if task
            else f"Reserved {_duration(booked)}: work stopped by the Business"
        ),
        minutes=0 if task else booked,
        paid_minor=paid,
        now=now,
    )
    kept = (
        charge.base_amount_minor
        - stop_worker_share(charge.base_amount_minor)
        - charge.worker_commission_minor
    )
    if kept > 0:
        await cancellation_repository.insert_worker_ledger(
            conn,
            worker_profile_id=assignment["worker_profile_id"],
            entry_type=LEDGER_ADJUSTMENT,
            amount_minor=-kept,
            currency=shift["currency"],
            assignment_id=assignment["id"],
            description=f"{PLATFORM_SHARE_PREFIX} (work stopped early): {shift['job_title']}",
        )
    refund_ids = await queue_split_refund(
        conn,
        shift["id"],
        max(paid - charge.total_minor, 0),
        live_refund_service.REASON_BUSINESS_CANCELLED,
        actor_user_id,
        assignment_id=assignment["id"],
    )
    await settle_status(conn, shift["id"], now, actor_user_id, "live_work_business_stopped")
    worker_gets = stop_worker_share(charge.base_amount_minor)
    await notify(
        conn,
        assignment["worker_user_id"],
        KIND_SHIFT_ENDED,
        "The Business stopped the work",
        f"{shift['job_title']} · you still get {live_work_billing.rupees(worker_gets)}.",
        {"shift_id": shift["id"], "assignment_id": assignment["id"], "live_work": True},
    )
    return refund_ids


async def restart_search(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    now: datetime,
    actor_user_id: UUID | None,
    reason: str,
) -> None:
    from app.services.shifts import live_dispatch_service

    settings = load_settings()
    radii = await catalog_service.search_radii(conn)
    await live_work_repository.start_search(
        conn,
        shift["id"],
        starts_at=now,
        ends_at=now + timedelta(minutes=pricing["reserved_minutes"]),
        radius_km=radii.live_initial_km,
        max_radius_km=radii.live_max_km,
        expires_at=now + timedelta(seconds=settings.live_search_timeout_seconds),
    )
    await shift_repository.record_history(
        conn, shift["id"], shift["status"], SHIFT_SEARCHING, actor_user_id, reason
    )
    await live_dispatch_service.dispatch_round(
        conn, await shift_repository.lock_shift(conn, shift["id"]), now
    )


async def settle_status(
    conn: asyncpg.Connection,
    shift_id: UUID,
    now: datetime,
    actor_user_id: UUID | None,
    reason: str,
) -> None:
    """Booking status from its seats once the search is over: filled (nobody started yet) →
    in_progress (someone started or finished) → completed (every remaining seat finished)."""
    shift = await shift_repository.lock_shift(conn, shift_id)
    if shift["status"] not in (SHIFT_FILLED, SHIFT_IN_PROGRESS):
        return
    seats = await live_work_repository.list_assignments(conn, shift_id)
    active = [a for a in seats if a["status"] in ACTIVE_SEAT_STATUSES]
    done = [a for a in seats if a["status"] in DONE_SEAT_STATUSES]
    if active:
        started = done or any(a["status"] == ASG_CHECKED_IN for a in active)
        target = SHIFT_IN_PROGRESS if started else SHIFT_FILLED
    elif done:
        target = SHIFT_COMPLETED
    else:
        return
    if target != shift["status"]:
        await shift_repository.set_status(
            conn,
            shift_id,
            from_status=shift["status"],
            to_status=target,
            now=now,
            actor_user_id=actor_user_id,
            reason=reason,
        )


async def release_seat(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment_id: UUID,
    amount_minor: int,
    reason: str,
    actor_user_id: UUID | None,
    now: datetime,
) -> list[UUID | None]:
    """The seat is gone for good: refund ``amount_minor`` from its ledger and drop it from the
    booking. A search still running keeps looking for the other seats; otherwise, with no
    Worker left, the empty seats are refunded and the booking is cancelled."""
    refund_ids = await queue_split_refund(
        conn, shift["id"], amount_minor, reason, actor_user_id, assignment_id=assignment_id
    )
    open_seats = max(shift["workers_required"] - 1, 0)
    if open_seats:
        await live_work_repository.set_shift_workers_required(conn, shift["id"], open_seats)
    seats = await live_work_repository.list_assignments(conn, shift["id"])
    taken = sum(1 for a in seats if a["status"] != "cancelled")
    searching = shift["status"] == SHIFT_SEARCHING
    if not taken and not (searching and open_seats):
        refund_ids += await queue_split_refund(
            conn,
            shift["id"],
            open_seats * pricing["total_minor"],
            reason,
            actor_user_id,
            deposit_only=True,
            scope="seats_closed",
        )
        await withdraw_offers(conn, shift["id"])
        await shift_repository.cancel_shift(conn, shift["id"], now=now, reason=reason)
        await shift_repository.record_history(
            conn, shift["id"], shift["status"], "cancelled", actor_user_id, reason
        )
    elif searching:
        if taken >= open_seats:
            current = await shift_repository.lock_shift(conn, shift["id"])
            await live_dispatch_service().mark_filled(conn, current, now, reason=reason)
    else:
        await settle_status(conn, shift["id"], now, actor_user_id, reason)
    return refund_ids


async def reopen_or_release_seat(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment_id: UUID,
    actor_user_id: UUID | None,
    now: datetime,
) -> tuple[str, list[UUID | None]]:
    """A Worker cancelled before starting. → ("restarted" | "reopened" | "released", refunds).

    * Nobody else holds a seat and nobody started: a fresh search (single-Worker behaviour).
    * Others hold seats, nobody started and the original search window is still open: the seat
      reopens inside that window.
    * Otherwise the seat's share is refunded and the booking keeps its other Workers."""
    seats = await live_work_repository.list_assignments(conn, shift["id"])
    others = [a for a in seats if a["id"] != assignment_id and a["status"] != "cancelled"]
    started = any(a["status"] not in BEFORE_START_SEAT_STATUSES for a in others)
    if not others:
        await restart_search(conn, shift, pricing, now, actor_user_id, "worker_cancelled_reassign")
        return "restarted", []
    expires_at = shift["search_expires_at"]
    if not started and expires_at is not None and expires_at > now:
        if shift["status"] != SHIFT_SEARCHING:
            await shift_repository.set_status(
                conn,
                shift["id"],
                from_status=shift["status"],
                to_status=SHIFT_SEARCHING,
                now=now,
                actor_user_id=actor_user_id,
                reason="worker_cancelled_reopen_seat",
            )
        await live_dispatch_service().dispatch_round(
            conn, await shift_repository.lock_shift(conn, shift["id"]), now
        )
        return "reopened", []
    refunds = await release_seat(
        conn,
        shift,
        pricing,
        assignment_id,
        pricing["total_minor"],
        live_refund_service.REASON_SEAT_RELEASED,
        actor_user_id,
        now,
    )
    return "released", refunds


def live_dispatch_service():  # type: ignore[no-untyped-def]
    from app.services.shifts import live_dispatch_service as module

    return module


async def apply_paid_extension(
    conn: asyncpg.Connection, invoice: asyncpg.Record, now: datetime
) -> list[UUID | None]:
    """Extension invoice paid: add the time, or refund if the extension can no longer apply."""
    ext = await live_work_repository.lock_extension_by_invoice(conn, invoice["id"])
    if ext is None:
        return []
    assignment = await assignment_repository.lock_context(conn, ext["assignment_id"])
    if ext["status"] == "awaiting_payment" and assignment["status"] == ASG_CHECKED_IN:
        await live_work_repository.set_extension_status(conn, ext["id"], "applied", now)
        await assignment_repository.add_extended_minutes(
            conn, ext["assignment_id"], ext["extra_minutes"]
        )
        pricing = await live_work_repository.get_booking_pricing(conn, ext["shift_id"])
        await live_work_repository.extend_shift_end_to(
            conn,
            ext["shift_id"],
            seat_ends_at(
                assignment["checked_in_at"],
                pricing["reserved_minutes"],
                assignment["extended_minutes"] + ext["extra_minutes"],
            ),
        )
        data = {
            "shift_id": ext["shift_id"],
            "assignment_id": ext["assignment_id"],
            "live_work": True,
        }
        text = f"+{_duration(ext['extra_minutes'])} added to {assignment['job_title']}"
        await notify(
            conn,
            assignment["worker_user_id"],
            KIND_EXTENSION_ANSWERED,
            "Extension paid",
            text,
            data,
        )
        await notify(
            conn,
            assignment["business_user_id"],
            KIND_EXTENSION_ANSWERED,
            "Extension added",
            text,
            data,
        )
        return []
    if ext["status"] == "applied":
        return []
    return [
        await live_refund_service.queue_refund(
            conn,
            shift_id=ext["shift_id"],
            invoice_id=invoice["id"],
            amount_minor=invoice["total_minor"],
            reason=live_refund_service.REASON_EXTENSION_VOID,
            actor_user_id=None,
        )
    ]


def seat_ends_at(checked_in_at: datetime, reserved_minutes: int, extended_minutes: int) -> datetime:
    return checked_in_at + timedelta(minutes=reserved_minutes + extended_minutes)


async def business_user_id(conn: asyncpg.Connection, shift: asyncpg.Record) -> UUID:
    row = await profile_repository.get_business_profile(conn, shift["business_profile_id"])
    return row["user_id"]


async def notify_cancelled(
    conn: asyncpg.Connection, user_id: UUID, title: str, body: str, data: dict
) -> None:
    await notify(conn, user_id, KIND_SHIFT_CANCELLED, title, body, data)


async def withdraw_offers(conn: asyncpg.Connection, shift_id: UUID) -> None:
    await dispatch_repository.withdraw_open_offers(conn, shift_id)
