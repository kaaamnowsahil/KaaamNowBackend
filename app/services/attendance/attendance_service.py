"""Geo + code check-in, check-out with recorded minutes, business review and no-show."""

from __future__ import annotations

import hmac
from datetime import timedelta
from uuid import UUID

from app.config.settings import load_settings
from app.constants.attendance.attendance_route_strings import (
    MSG_APPROVED_MINUTES_TOO_HIGH,
    MSG_CHECK_IN_CLOSED,
    MSG_CHECK_IN_CODE,
    MSG_CHECK_IN_NOT_OPEN,
    MSG_CHECK_IN_TOO_FAR,
    MSG_NO_SHOW_TOO_EARLY,
    MSG_NOT_CHECKED_IN,
    MSG_NOT_CHECKED_OUT,
)
from app.constants.notifications.notification_route_strings import (
    KIND_ATTENDANCE_APPROVED,
    KIND_NO_SHOW,
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
    MSG_ASSIGNMENT_NOT_FOUND,
    MSG_ASSIGNMENT_STATE,
    SHIFT_FILLED,
    SHIFT_IN_PROGRESS,
    SHIFT_OPEN,
    SHIFT_SEARCHING,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.repositories.attendance import attendance_repository
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
)
from app.schemas.shifts.assignment_schemas import AssignmentDetail
from app.security.authenticated_user import AuthenticatedUser
from app.services.notifications.notification_service import notify
from app.services.shifts.assignment_service import (
    PARTY_BUSINESS,
    PARTY_WORKER,
    build_assignment_detail,
    check_in_opens_at,
    load_context,
)
from app.utils.clock import minutes_between, utc_now
from app.utils.geo import haversine_km


def recorded_minutes(ctx, checked_in_at, checked_out_at) -> int:  # type: ignore[no-untyped-def]
    """Payable minutes inside the scheduled window, minus the scheduled break."""
    start = max(checked_in_at, ctx["starts_at"])
    end = min(checked_out_at, ctx["ends_at"])
    return max(minutes_between(start, end) - ctx["break_minutes"], 0)


def scheduled_paid_minutes(ctx) -> int:  # type: ignore[no-untyped-def]
    return max(minutes_between(ctx["starts_at"], ctx["ends_at"]) - ctx["break_minutes"], 0)


async def check_in(
    user: AuthenticatedUser, assignment_id: UUID, body: CheckInRequest
) -> AssignmentDetail:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            if party != PARTY_WORKER:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] not in ASG_BOOKED_STATUSES:
                raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
            if now < check_in_opens_at(ctx):
                raise conflict("check_in_not_open", MSG_CHECK_IN_NOT_OPEN)
            if now >= ctx["ends_at"]:
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
            if not hmac.compare_digest(body.check_in_code, ctx["check_in_code"]):
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


async def check_out(
    user: AuthenticatedUser, assignment_id: UUID, body: CheckOutRequest
) -> AssignmentDetail:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            if party != PARTY_WORKER:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] != ASG_CHECKED_IN:
                raise conflict("not_checked_in", MSG_NOT_CHECKED_IN)
            minutes = recorded_minutes(ctx, ctx["checked_in_at"], now)
            await attendance_repository.set_check_out(
                conn,
                assignment_id,
                now=now,
                latitude=body.latitude,
                longitude=body.longitude,
                note=body.note,
                recorded_minutes=minutes,
            )
            await assignment_repository.set_status(conn, assignment_id, ASG_CHECKED_OUT)
            await notify(
                conn,
                ctx["business_user_id"],
                KIND_WORKER_CHECKED_OUT,
                "Worker checked out — review attendance",
                f"{ctx['job_title']} · {minutes // 60}h {minutes % 60}m recorded",
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
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] != ASG_CHECKED_OUT:
                raise conflict("not_checked_out", MSG_NOT_CHECKED_OUT)
            minutes = (
                body.approved_minutes
                if body.approved_minutes is not None
                else ctx["recorded_minutes"]
            )
            if minutes > scheduled_paid_minutes(ctx):
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
            if party != PARTY_BUSINESS:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] not in ASG_BOOKED_STATUSES:
                raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
            if now < ctx["starts_at"] + timedelta(minutes=settings.no_show_grace_minutes):
                raise conflict("no_show_too_early", MSG_NO_SHOW_TOO_EARLY)
            await assignment_repository.set_status(conn, assignment_id, ASG_NO_SHOW)
            await notify(
                conn,
                ctx["worker_user_id"],
                KIND_NO_SHOW,
                "Marked as no-show",
                f"You didn't check in for {ctx['job_title']}.",
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)
