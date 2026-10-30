"""Live Work state transitions shared by Business, Worker, payment hooks and sweeps.

Cancellation money follows docs/marketplace-rules.md through the active cancellation policy
tiers (admin-configurable). A Live Work booking starts as soon as a Worker accepts, so the
"time before start" is 0 and the "less than 2 hours" tiers apply:

* Business, no Worker yet          → free; full refund (rules §6).
* Business, Worker assigned        → business cancel tier on the base amount; commission and tax
                                     are kept only on that fee; the Worker share is credited (§6).
* Worker, before starting          → worker cancel tier (fee, strike, Business voucher); the
                                     Business keeps its booking and the search restarts (§5).
* Worker, after starting (walk-off)→ Business pays worked time only; the rest is refunded; the
                                     Worker pays the walk-off fee; Business voucher (§8).

Reserved time is always billed when work completes, even early (Live Work rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_EXTENSION_ANSWERED,
    KIND_SHIFT_CANCELLED,
    KIND_SHIFT_ENDED,
    KIND_WORKER_CHECKED_OUT,
)
from app.constants.shifts.shift_route_strings import (
    ASG_CHECKED_IN,
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


async def paid_total(conn: asyncpg.Connection, shift_id: UUID) -> int:
    return sum(i["total_minor"] for i in await live_work_billing.paid_invoices(conn, shift_id))


@dataclass(frozen=True)
class CancelPlan:
    party: str
    stage: str
    quote: SeatQuote | None
    refund_minor: int
    rule: str
    effect: str


async def business_cancel_plan(
    conn: asyncpg.Connection,
    shift: asyncpg.Record,
    pricing: asyncpg.Record,
    assignment: asyncpg.Record | None,
) -> CancelPlan:
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
    if status == SHIFT_SEARCHING:
        return CancelPlan(
            PARTY_BUSINESS,
            "before_acceptance",
            None,
            await paid_total(conn, shift["id"]),
            "Rules §6: no Worker assigned yet — free cancellation, full refund.",
            "The search stops and the full amount is refunded to your payment method.",
        )
    if (
        status != SHIFT_FILLED
        or assignment is None
        or assignment["status"]
        not in (
            "confirmed",
            "en_route",
        )
    ):
        raise state_error({"stage": status})
    policy = await cancellation_service.load_policy(conn)
    tier = pick_tier(policy, PARTY_BUSINESS, EVENT_CANCEL, Decimal(0))
    base = pricing["base_amount_minor"]
    fee = min(tier_fee(tier, base), base)
    retained = _charge(pricing, fee).total_minor if fee else 0
    paid = await paid_total(conn, shift["id"])
    compensation = min(platform_fee(base, tier.worker_share_pct), fee) if tier else 0
    quote = SeatQuote(
        party=PARTY_BUSINESS,
        event=EVENT_CANCEL,
        hours_before=Decimal(0),
        booking_minor=base,
        fee_minor=fee,
        worker_compensation_minor=compensation,
        business_refund_minor=max(paid - retained, 0),
        business_retained_minor=min(retained, paid),
        strike_weight=Decimal(0),
        business_voucher=False,
        policy_version=policy.version,
    )
    return CancelPlan(
        PARTY_BUSINESS,
        "before_start",
        quote,
        quote.business_refund_minor,
        "Rules §6: Worker already assigned and on the way (less than 2 hours before start) — "
        "cancellation fee on the base amount; part of it goes to the Worker.",
        "The Worker is released and the rest of your payment is refunded.",
    )


def _is_task(pricing: asyncpg.Record) -> bool:
    return pricing["pricing_mode"] == PRICING_TASK


def _worked_base(pricing: asyncpg.Record, worked_minutes: int) -> int:
    """Hourly walk-off: worked time is paid. Task walk-off: the job isn't done, nothing is."""
    if _is_task(pricing):
        return 0
    reserved = pricing["reserved_minutes"]
    regular = min(worked_minutes, reserved)
    extra = max(worked_minutes - reserved, 0)
    return pay_for_minutes(pricing["hourly_rate_minor"], regular) + extension_base(
        pricing["hourly_rate_minor"], extra, Decimal(pricing["extension_surcharge_pct"])
    )


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
    cap = pricing["reserved_minutes"] + assignment["extended_minutes"]
    worked = min(minutes_between(assignment["checked_in_at"], now), cap)
    charge = _charge(pricing, _worked_base(pricing, worked), with_coupon=True)
    paid = await paid_total(conn, pricing["shift_id"])
    tier = pick_tier(policy, PARTY_WORKER, EVENT_WALK_OFF, Decimal(0))
    quote = SeatQuote(
        party=PARTY_WORKER,
        event=EVENT_WALK_OFF,
        hours_before=Decimal(0),
        booking_minor=base,
        fee_minor=tier_fee(tier, base),
        worker_compensation_minor=0,
        business_refund_minor=max(paid - charge.total_minor, 0),
        business_retained_minor=min(charge.total_minor, paid),
        strike_weight=tier.strike_weight if tier else Decimal(0),
        business_voucher=tier.business_voucher if tier else False,
        policy_version=policy.version,
    )
    rule, effect = (
        (
            "Rules §8: Worker stops before the task is done (walk-off) — the Business is "
            "refunded in full; the Worker pays the walk-off fee.",
            "The task price is not paid; the Business gets its money back.",
        )
        if _is_task(pricing)
        else (
            "Rules §8: Worker stops before the booked time ends (walk-off) — the Business pays "
            "worked time only; the Worker pays the walk-off fee.",
            "Your worked time is paid; the unworked amount is refunded to the Business.",
        )
    )
    return (
        CancelPlan(PARTY_WORKER, "during_work", quote, quote.business_refund_minor, rule, effect),
        worked,
    )


async def queue_split_refund(
    conn: asyncpg.Connection,
    shift_id: UUID,
    amount_minor: int,
    reason: str,
    actor_user_id: UUID | None,
) -> list[UUID | None]:
    """Refund ``amount_minor`` across paid invoices, newest payment first."""
    ids: list[UUID | None] = []
    remaining = amount_minor
    for invoice in await live_work_billing.paid_invoices(conn, shift_id):
        if remaining <= 0:
            break
        part = min(remaining, invoice["total_minor"])
        ids.append(
            await live_refund_service.queue_refund(
                conn,
                shift_id=shift_id,
                invoice_id=invoice["id"],
                amount_minor=part,
                reason=reason,
                actor_user_id=actor_user_id,
            )
        )
        remaining -= part
    return ids


async def close_open_extensions(conn: asyncpg.Connection, shift_id: UUID, now: datetime) -> None:
    for ext in await live_work_repository.list_extensions(conn, shift_id):
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
) -> None:
    """Complete Work: bill reserved + applied extensions (never less), or the fixed task price,
    and credit the Worker."""
    if assignment["status"] != ASG_CHECKED_IN or shift["status"] != SHIFT_IN_PROGRESS:
        raise state_error({"stage": assignment["status"]})
    task = _is_task(pricing)
    await completion_codes.mark_used(conn, assignment["id"], now)
    await close_open_extensions(conn, shift["id"], now)
    applied = [
        e
        for e in await live_work_repository.list_extensions(conn, shift["id"])
        if e["status"] == "applied" and e["assignment_id"] == assignment["id"]
    ]
    ext_minutes = sum(e["extra_minutes"] for e in applied)
    charge = completed_charge(
        live_work_billing.snapshot_charge(pricing),
        [live_work_billing.extension_snapshot_charge(e) for e in applied],
        Decimal(pricing["commission_pct"]),
    )
    worked = minutes_between(assignment["checked_in_at"], now)
    billed_minutes = worked if task else pricing["reserved_minutes"] + ext_minutes
    await attendance_repository.set_check_out(
        conn,
        assignment["id"],
        now=now,
        latitude=None,
        longitude=None,
        note=f"Live Work completed by {ended_by}",
        recorded_minutes=worked,
    )
    await attendance_repository.approve(
        conn,
        assignment["id"],
        approved_minutes=billed_minutes,
        note="Live Work: task completed" if task else "Live Work: reserved time billed in full",
        now=now,
        approver_user_id=actor_user_id or assignment["worker_user_id"],
    )
    await assignment_repository.set_ended(
        conn, assignment["id"], END_COMPLETED if task else END_SCHEDULED
    )
    await live_work_repository.set_assignment_approved(conn, assignment["id"])
    if task:
        description = "Task completed (fixed price)"
    else:
        description = f"Reserved {_duration(pricing['reserved_minutes'])}"
        if ext_minutes:
            description += f" + extensions {_duration(ext_minutes)}"
    await live_work_billing.create_final_invoice(
        conn,
        pricing,
        assignment_id=assignment["id"],
        charge=charge,
        description=description,
        minutes=billed_minutes,
        paid_minor=await paid_total(conn, shift["id"]),
        now=now,
    )
    await shift_repository.set_status(
        conn,
        shift["id"],
        from_status=SHIFT_IN_PROGRESS,
        to_status=SHIFT_COMPLETED,
        now=now,
        actor_user_id=actor_user_id,
        reason=f"live_work_completed_by_{ended_by}",
    )
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
    await completion_codes.mark_used(conn, assignment["id"], now)
    await close_open_extensions(conn, shift["id"], now)
    base = _worked_base(pricing, worked)
    charge = _charge(pricing, base, with_coupon=True)
    paid = await paid_total(conn, shift["id"])
    await attendance_repository.set_check_out(
        conn,
        assignment["id"],
        now=now,
        latitude=None,
        longitude=None,
        note="Worker stopped work early",
        recorded_minutes=worked,
    )
    await attendance_repository.approve(
        conn,
        assignment["id"],
        approved_minutes=worked,
        note="Live Work walk-off: worked time only",
        now=now,
        approver_user_id=actor_user_id,
    )
    await assignment_repository.set_ended(conn, assignment["id"], END_WORKER_LEFT)
    await live_work_repository.set_assignment_approved(conn, assignment["id"])
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
        charge=charge,
        description=(
            "Task not completed (Worker left)"
            if _is_task(pricing)
            else f"Worked {_duration(worked)} of {_duration(pricing['reserved_minutes'])}"
        ),
        minutes=worked,
        paid_minor=paid,
        now=now,
    )
    await shift_repository.set_status(
        conn,
        shift["id"],
        from_status=SHIFT_IN_PROGRESS,
        to_status=SHIFT_COMPLETED,
        now=now,
        actor_user_id=actor_user_id,
        reason="live_work_worker_left",
    )
    refund_ids = await queue_split_refund(
        conn,
        shift["id"],
        max(paid - charge.total_minor, 0),
        live_refund_service.REASON_WORKER_LEFT,
        actor_user_id,
    )
    await notify(
        conn,
        await business_user_id(conn, shift),
        KIND_SHIFT_ENDED,
        "The Worker stopped work early",
        f"{shift['job_title']} · "
        + (
            "the task wasn't done, so it is refunded in full."
            if _is_task(pricing)
            else "you pay worked time only; the rest is refunded."
        ),
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
        await live_work_repository.extend_shift_end(conn, ext["shift_id"], ext["extra_minutes"])
        await assignment_repository.add_extended_minutes(
            conn, ext["assignment_id"], ext["extra_minutes"]
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


async def business_user_id(conn: asyncpg.Connection, shift: asyncpg.Record) -> UUID:
    row = await profile_repository.get_business_profile(conn, shift["business_profile_id"])
    return row["user_id"]


async def notify_cancelled(
    conn: asyncpg.Connection, user_id: UUID, title: str, body: str, data: dict
) -> None:
    await notify(conn, user_id, KIND_SHIFT_CANCELLED, title, body, data)


async def withdraw_offers(conn: asyncpg.Connection, shift_id: UUID) -> None:
    await dispatch_repository.withdraw_open_offers(conn, shift_id)
