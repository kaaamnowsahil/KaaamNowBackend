"""Geo + code check-in, check-out with recorded minutes, business review and no-show."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.attendance.attendance_route_strings import (
    MSG_APPROVED_MINUTES_TOO_HIGH,
    MSG_CHECK_IN_CLOSED,
    MSG_CHECK_IN_CODE,
    MSG_CHECK_IN_NOT_OPEN,
    MSG_CHECK_IN_TOO_FAR,
    MSG_EARLY_END_PIN_INVALID,
    MSG_EARLY_END_PIN_REQUIRED,
    MSG_EXTENSION_PENDING,
    MSG_EXTENSION_STATE,
    MSG_NO_SHOW_TOO_EARLY,
    MSG_NOT_CHECKED_IN,
    MSG_NOT_CHECKED_OUT,
)
from app.constants.notifications.notification_route_strings import (
    KIND_ATTENDANCE_APPROVED,
    KIND_EARLY_END_REQUESTED,
    KIND_EXTENSION_ANSWERED,
    KIND_EXTENSION_REQUESTED,
    KIND_NO_SHOW,
    KIND_SHIFT_ENDED,
    KIND_WORKER_CHECKED_IN,
    KIND_WORKER_CHECKED_OUT,
)
from app.constants.shifts.shift_route_strings import (
    APP_EXPIRED,
    ASG_APPROVED,
    ASG_BOOKED_STATUSES,
    ASG_CHECKED_IN,
    ASG_CHECKED_OUT,
    ASG_NO_SHOW,
    END_BUSINESS_STOPPED,
    END_MUTUAL,
    END_SCHEDULED,
    END_WORKER_LEFT,
    EXTENSION_ACCEPTED,
    EXTENSION_DECLINED,
    EXTENSION_REQUESTED,
    MSG_ASSIGNMENT_NOT_FOUND,
    MSG_ASSIGNMENT_STATE,
    SHIFT_COMPLETED,
    SHIFT_FILLED,
    SHIFT_IN_PROGRESS,
    SHIFT_LIVE,
    SHIFT_OPEN,
    SHIFT_SEARCHING,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.repositories.attendance import attendance_repository
from app.repositories.cancellations import cancellation_repository
from app.repositories.profiles import profile_repository
from app.repositories.shifts import (
    application_repository,
    assignment_repository,
    dispatch_repository,
    shift_repository,
)
from app.schemas.attendance.attendance_schemas import (
    AttendanceApproveRequest,
    CheckInRequest,
    CheckOutRequest,
    EarlyEndRequest,
    ExtensionRequest,
    ExtensionView,
    StopWorkRequest,
)
from app.schemas.shifts.assignment_schemas import AssignmentDetail
from app.security.authenticated_user import AuthenticatedUser
from app.services.cancellations import cancellation_service
from app.services.cancellations.cancellation_rules import EVENT_NO_SHOW, EVENT_WALK_OFF
from app.services.cancellations.cancellation_service import LEDGER_ADJUSTMENT
from app.services.catalog import catalog_service
from app.services.live_work import live_work_hooks
from app.services.notifications.notification_service import notify
from app.services.shifts.assignment_service import (
    PARTY_BUSINESS,
    PARTY_WORKER,
    build_assignment_detail,
    can_end_without_pin,
    check_in_opens_at,
    effective_ends_at,
    extension_view,
    load_context,
)
from app.utils.clock import minutes_between, utc_now
from app.utils.geo import haversine_km
from app.utils.money import platform_fee, worker_commission
from app.utils.references import new_numeric_code

EARLY_END_PIN_LENGTH = 4


def recorded_minutes(ctx, checked_in_at, checked_out_at) -> int:  # type: ignore[no-untyped-def]
    """Payable minutes inside the booked window (minus the break) plus time worked inside an
    accepted extension (overtime)."""
    start = max(checked_in_at, ctx["starts_at"])
    end = min(checked_out_at, ctx["ends_at"])
    regular = max(minutes_between(start, end) - ctx["break_minutes"], 0) if end > start else 0
    overtime_start = max(checked_in_at, ctx["ends_at"])
    overtime_end = min(checked_out_at, effective_ends_at(ctx))
    overtime = minutes_between(overtime_start, overtime_end) if overtime_end > overtime_start else 0
    return regular + overtime


def scheduled_paid_minutes(ctx) -> int:  # type: ignore[no-untyped-def]
    return max(minutes_between(ctx["starts_at"], ctx["ends_at"]) - ctx["break_minutes"], 0)


def payable_cap_minutes(ctx) -> int:  # type: ignore[no-untyped-def]
    return scheduled_paid_minutes(ctx) + ctx["extended_minutes"]


async def check_in(
    user: AuthenticatedUser, assignment_id: UUID, body: CheckInRequest
) -> AssignmentDetail:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_WORKER:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] not in ASG_BOOKED_STATUSES:
                raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
            if now < check_in_opens_at(ctx):
                raise conflict("check_in_not_open", MSG_CHECK_IN_NOT_OPEN)
            if now >= effective_ends_at(ctx):
                raise conflict("check_in_closed", MSG_CHECK_IN_CLOSED)
            distance_m = int(
                round(
                    haversine_km(
                        body.latitude, body.longitude, ctx["shift_latitude"], ctx["shift_longitude"]
                    )
                    * 1000
                )
            )
            if distance_m > settings.check_in_radius_m:
                raise bad_request(
                    "check_in_too_far",
                    MSG_CHECK_IN_TOO_FAR,
                    {"distance_m": distance_m, "allowed_m": settings.check_in_radius_m},
                )
            expected = (
                ctx["shift_check_in_code"]
                if ctx["shift_type"] == SHIFT_LIVE or not ctx["check_in_code"]
                else ctx["check_in_code"]
            )
            if not hmac.compare_digest(body.check_in_code.upper(), expected.upper()):
                raise bad_request("check_in_code_invalid", MSG_CHECK_IN_CODE)
            await attendance_repository.insert_check_in(
                conn,
                assignment_id,
                now=now,
                latitude=body.latitude,
                longitude=body.longitude,
                distance_m=distance_m,
            )
            await assignment_repository.set_status(conn, assignment_id, ASG_CHECKED_IN)
            await profile_repository.upsert_worker_location(
                conn,
                ctx["worker_profile_id"],
                latitude=body.latitude,
                longitude=body.longitude,
                accuracy_m=None,
                recorded_at=now,
            )
            shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
            if shift["status"] in (SHIFT_SEARCHING, SHIFT_OPEN, SHIFT_FILLED):
                await shift_repository.set_status(
                    conn,
                    shift["id"],
                    from_status=shift["status"],
                    to_status=SHIFT_IN_PROGRESS,
                    now=now,
                    actor_user_id=user.user_id,
                    reason="first_check_in",
                )
                await dispatch_repository.withdraw_open_offers(conn, shift["id"])
                await application_repository.close_open_applications(
                    conn, shift["id"], status=APP_EXPIRED, now=now
                )
            await notify(
                conn,
                ctx["business_user_id"],
                KIND_WORKER_CHECKED_IN,
                "Worker checked in",
                ctx["job_title"],
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)


async def _complete_shift_if_done(conn: asyncpg.Connection, shift_id: UUID, now: datetime) -> None:
    """An in-progress shift is completed once nobody is still booked, travelling or working.
    Hours approval and the final invoice still happen on the completed shift."""
    shift = await shift_repository.lock_shift(conn, shift_id)
    if shift is None or shift["status"] != SHIFT_IN_PROGRESS:
        return
    active = await assignment_repository.count_in(
        conn, shift_id, [*ASG_BOOKED_STATUSES, ASG_CHECKED_IN]
    )
    if active:
        return
    await shift_repository.set_status(
        conn,
        shift_id,
        from_status=SHIFT_IN_PROGRESS,
        to_status=SHIFT_COMPLETED,
        now=now,
        reason="all_workers_finished",
    )


async def _finish(
    conn: asyncpg.Connection,
    ctx: asyncpg.Record,
    *,
    party: str,
    reason: str,
    now: datetime,
    note: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    minutes: int | None = None,
) -> int:
    """Stop the timer: record minutes, close the booking, tell the other side."""
    if minutes is None:
        minutes = recorded_minutes(ctx, ctx["checked_in_at"], now)
    await attendance_repository.set_check_out(
        conn,
        ctx["id"],
        now=now,
        latitude=latitude,
        longitude=longitude,
        note=note,
        recorded_minutes=minutes,
    )
    await assignment_repository.set_ended(conn, ctx["id"], reason)
    await assignment_repository.expire_open_extensions(conn, ctx["id"], now)
    await _complete_shift_if_done(conn, ctx["shift_id"], now)
    data = {"shift_id": ctx["shift_id"], "assignment_id": ctx["id"]}
    worked = f"{ctx['job_title']} · {minutes // 60}h {minutes % 60}m recorded"
    if party == PARTY_WORKER:
        await notify(
            conn,
            ctx["business_user_id"],
            KIND_WORKER_CHECKED_OUT,
            "Worker checked out — review attendance",
            worked,
            data,
        )
    else:
        await notify(
            conn, ctx["worker_user_id"], KIND_SHIFT_ENDED, "Your shift was ended", worked, data
        )
    return minutes


def _require_checked_in(ctx: asyncpg.Record) -> None:
    if ctx["status"] != ASG_CHECKED_IN:
        raise conflict("not_checked_in", MSG_NOT_CHECKED_IN)


async def check_out(
    user: AuthenticatedUser, assignment_id: UUID, body: CheckOutRequest
) -> AssignmentDetail:
    """Worker ends at the booked end time. Earlier needs the business's PIN (end-early)."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_WORKER:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            _require_checked_in(ctx)
            if not can_end_without_pin(ctx, now):
                raise conflict("early_end_pin_required", MSG_EARLY_END_PIN_REQUIRED)
            await _finish(
                conn,
                ctx,
                party=party,
                reason=END_SCHEDULED,
                now=now,
                note=body.note,
                latitude=body.latitude,
                longitude=body.longitude,
            )
            return await build_assignment_detail(conn, assignment_id, user)


async def business_end(user: AuthenticatedUser, assignment_id: UUID) -> AssignmentDetail:
    """Business ends at the booked end time (same rule as the worker's check-out)."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            _require_checked_in(ctx)
            if not can_end_without_pin(ctx, now):
                raise conflict("early_end_pin_required", MSG_EARLY_END_PIN_REQUIRED)
            await _finish(conn, ctx, party=party, reason=END_SCHEDULED, now=now)
            return await build_assignment_detail(conn, assignment_id, user)


async def request_early_end(
    user: AuthenticatedUser, assignment_id: UUID, *, as_party: str
) -> AssignmentDetail:
    """Show a one-time PIN in the OTHER side's app; the requester enters it to end early."""
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != as_party:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            _require_checked_in(ctx)
            pin = new_numeric_code(EARLY_END_PIN_LENGTH)
            await assignment_repository.set_early_end_pin(
                conn,
                assignment_id,
                pin=pin,
                requested_by=party,
                expires_at=now + timedelta(minutes=settings.early_end_pin_valid_minutes),
            )
            other = ctx["business_user_id"] if party == PARTY_WORKER else ctx["worker_user_id"]
            asker = "Your worker" if party == PARTY_WORKER else ctx["business_name"]
            await notify(
                conn,
                other,
                KIND_EARLY_END_REQUESTED,
                f"{asker} wants to end {ctx['job_title']} early",
                f"Share PIN {pin} only if you agree. Payment is for the time worked.",
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)


async def end_early(
    user: AuthenticatedUser, assignment_id: UUID, body: EarlyEndRequest, *, as_party: str
) -> AssignmentDetail:
    """Both agreed (PIN from the other side): pay actual worked time."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != as_party:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            _require_checked_in(ctx)
            valid = (
                ctx["early_end_pin"] is not None
                and ctx["early_end_requested_by"] == party
                and ctx["early_end_pin_expires_at"] > now
                and hmac.compare_digest(body.pin, ctx["early_end_pin"])
            )
            if not valid:
                raise bad_request("early_end_pin_invalid", MSG_EARLY_END_PIN_INVALID)
            await _finish(conn, ctx, party=party, reason=END_MUTUAL, now=now, note=body.note)
            return await build_assignment_detail(conn, assignment_id, user)


async def stop_work(
    user: AuthenticatedUser, assignment_id: UUID, body: StopWorkRequest
) -> AssignmentDetail:
    """Business ends without the worker's agreement (rules §8). Disputes go to support."""
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            _require_checked_in(ctx)
            shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
            if body.reason == END_BUSINESS_STOPPED:
                full = payable_cap_minutes(ctx)
                await _finish(
                    conn,
                    ctx,
                    party=party,
                    reason=END_BUSINESS_STOPPED,
                    now=now,
                    note=body.note,
                    minutes=full,
                )
                await attendance_repository.approve(
                    conn,
                    assignment_id,
                    approved_minutes=full,
                    note=body.note,
                    now=now,
                    approver_user_id=user.user_id,
                )
                await assignment_repository.set_status(conn, assignment_id, ASG_APPROVED)
                rates = catalog_service.shift_rates(shift) or await catalog_service.active_rates(
                    conn
                )
                booking = cancellation_service.seat_booking_minor(shift, ctx["hourly_rate_minor"])
                kept = platform_fee(
                    booking, Decimal(100 - settings.business_stop_worker_share_pct)
                ) - worker_commission(booking, rates)
                if kept > 0:
                    await cancellation_repository.insert_worker_ledger(
                        conn,
                        worker_profile_id=ctx["worker_profile_id"],
                        entry_type=LEDGER_ADJUSTMENT,
                        amount_minor=-kept,
                        currency=shift["currency"],
                        assignment_id=assignment_id,
                        description=f"Platform share (work stopped early): {ctx['job_title']}",
                    )
            else:
                await _finish(
                    conn, ctx, party=party, reason=END_WORKER_LEFT, now=now, note=body.note
                )
                quote = await cancellation_service.quote_assignment(
                    conn,
                    shift,
                    ctx["hourly_rate_minor"],
                    party=PARTY_WORKER,
                    event=EVENT_WALK_OFF,
                    now=now,
                )
                await cancellation_service.apply_seat(
                    conn,
                    shift=shift,
                    assignment_id=assignment_id,
                    worker_profile_id=ctx["worker_profile_id"],
                    worker_user_id=ctx["worker_user_id"],
                    quote=quote,
                    actor_user_id=user.user_id,
                    now=now,
                    seat_reopens=True,
                )
            return await build_assignment_detail(conn, assignment_id, user)


async def request_extension(
    user: AuthenticatedUser, assignment_id: UUID, body: ExtensionRequest
) -> ExtensionView:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            _require_checked_in(ctx)
            if await assignment_repository.lock_open_extension(conn, assignment_id):
                raise conflict("extension_pending", MSG_EXTENSION_PENDING)
            extension_id = await assignment_repository.insert_extension(
                conn,
                assignment_id,
                extra_minutes=body.extra_minutes,
                requested_by_user_id=user.user_id,
                now=now,
            )
            await notify(
                conn,
                ctx["worker_user_id"],
                KIND_EXTENSION_REQUESTED,
                f"Extend {ctx['job_title']} by {body.extra_minutes} min?",
                f"{ctx['business_name']} asked. Extra time is paid at "
                f"{load_settings().overtime_rate_pct}% of your rate.",
                {
                    "shift_id": ctx["shift_id"],
                    "assignment_id": assignment_id,
                    "extension_id": extension_id,
                },
            )
            row = await assignment_repository.lock_extension(conn, extension_id)
            return extension_view(row)


async def respond_extension(
    user: AuthenticatedUser, assignment_id: UUID, extension_id: UUID, *, accept: bool
) -> AssignmentDetail:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_WORKER:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            extension = await assignment_repository.lock_extension(conn, extension_id)
            if (
                extension is None
                or extension["assignment_id"] != assignment_id
                or extension["status"] != EXTENSION_REQUESTED
            ):
                raise conflict("extension_state", MSG_EXTENSION_STATE)
            _require_checked_in(ctx)
            status = EXTENSION_ACCEPTED if accept else EXTENSION_DECLINED
            await assignment_repository.set_extension_status(conn, extension_id, status, now)
            if accept:
                await assignment_repository.add_extended_minutes(
                    conn, assignment_id, extension["extra_minutes"]
                )
            await notify(
                conn,
                ctx["business_user_id"],
                KIND_EXTENSION_ANSWERED,
                f"Extension {'accepted' if accept else 'declined'}",
                f"{ctx['job_title']} · {extension['extra_minutes']} min",
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)


async def approve(
    user: AuthenticatedUser, assignment_id: UUID, body: AttendanceApproveRequest
) -> AssignmentDetail:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] != ASG_CHECKED_OUT:
                raise conflict("not_checked_out", MSG_NOT_CHECKED_OUT)
            minutes = (
                body.approved_minutes
                if body.approved_minutes is not None
                else ctx["recorded_minutes"]
            )
            if minutes > payable_cap_minutes(ctx):
                raise bad_request("approved_minutes_too_high", MSG_APPROVED_MINUTES_TOO_HIGH)
            await attendance_repository.approve(
                conn,
                assignment_id,
                approved_minutes=minutes,
                note=body.note,
                now=now,
                approver_user_id=user.user_id,
            )
            await assignment_repository.set_status(conn, assignment_id, ASG_APPROVED)
            await notify(
                conn,
                ctx["worker_user_id"],
                KIND_ATTENDANCE_APPROVED,
                "Your hours were approved",
                f"{ctx['job_title']} · {minutes // 60}h {minutes % 60}m",
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)


async def mark_no_show(user: AuthenticatedUser, assignment_id: UUID) -> AssignmentDetail:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            await live_work_hooks.reject_generic_action(conn, ctx["shift_id"])
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] not in ASG_BOOKED_STATUSES:
                raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
            if now < ctx["starts_at"] + timedelta(minutes=settings.no_show_grace_minutes):
                raise conflict("no_show_too_early", MSG_NO_SHOW_TOO_EARLY)
            await assignment_repository.set_status(conn, assignment_id, ASG_NO_SHOW)
            if ctx["shift_type"] != SHIFT_LIVE:
                shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
                await cancellation_service.apply_seat(
                    conn,
                    shift=shift,
                    assignment_id=assignment_id,
                    worker_profile_id=ctx["worker_profile_id"],
                    worker_user_id=ctx["worker_user_id"],
                    quote=await cancellation_service.quote_assignment(
                        conn,
                        shift,
                        ctx["hourly_rate_minor"],
                        party=PARTY_WORKER,
                        event=EVENT_NO_SHOW,
                        now=now,
                    ),
                    actor_user_id=user.user_id,
                    now=now,
                )
            await _complete_shift_if_done(conn, ctx["shift_id"], now)
            await notify(
                conn,
                ctx["worker_user_id"],
                KIND_NO_SHOW,
                "Marked as no-show",
                f"You didn't check in for {ctx['job_title']}.",
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)
