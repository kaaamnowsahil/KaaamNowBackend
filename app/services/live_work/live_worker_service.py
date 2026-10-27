"""Worker side of Live Work: Available requests, Accept Work, travel, arrival code, Complete Work,
cancellation and Extend Work answers. The arrival code itself is never sent to the Worker."""

from __future__ import annotations

import hmac
from datetime import timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_EXTENSION_ANSWERED,
    KIND_WORKER_CHECKED_IN,
    KIND_WORKER_EN_ROUTE,
)
from app.constants.shifts.shift_route_strings import (
    ASG_CHECKED_IN,
    ASG_CONFIRMED,
    SHIFT_FILLED,
    SHIFT_IN_PROGRESS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request, conflict, not_found
from app.pagination import clamp_page_limit
from app.repositories.attendance import attendance_repository
from app.repositories.live_work import live_work_repository
from app.repositories.profiles import profile_repository
from app.repositories.shifts import assignment_repository, shift_repository
from app.schemas.live_work.live_work_schemas import (
    LiveCancelPreview,
    LiveCancelRequest,
    LiveExtensionAnswer,
    LiveLocationUpdate,
    LiveStartWork,
    WorkerActiveLiveWork,
    WorkerLiveBooking,
    WorkerLiveRequest,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.cancellations import cancellation_service
from app.services.live_work import live_refund_service, live_work_billing, live_work_core
from app.services.live_work.live_work_service import cancel_preview_view
from app.services.live_work.live_work_views import build_worker_state, cancel_reason
from app.services.notifications.notification_service import notify
from app.services.profiles.profile_lookup import require_worker_profile
from app.services.shifts import live_dispatch_service
from app.utils.clock import utc_now
from app.utils.geo import haversine_km


async def _owned_assignment(
    conn: asyncpg.Connection, user: AuthenticatedUser, assignment_id: UUID, *, lock: bool
) -> tuple[asyncpg.Record, asyncpg.Record]:
    """→ (worker profile, assignment context) for a Live Work assignment of this Worker."""
    worker = await require_worker_profile(conn, user.user_id)
    ctx = await (
        assignment_repository.lock_context(conn, assignment_id)
        if lock
        else assignment_repository.get_context(conn, assignment_id)
    )
    if (
        ctx is None
        or ctx["worker_profile_id"] != worker["id"]
        or not await live_work_repository.is_live_work(conn, ctx["shift_id"])
    ):
        raise live_work_core.not_found_error()
    return worker, ctx


async def _state(conn: asyncpg.Connection, assignment_id: UUID) -> WorkerLiveBooking:
    ctx = await assignment_repository.get_context(conn, assignment_id)
    return await build_worker_state(conn, ctx, utc_now())


async def list_requests(user: AuthenticatedUser) -> list[WorkerLiveRequest]:
    now = utc_now()
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        items: list[WorkerLiveRequest] = []
        for offer in await live_work_repository.list_open_offers_for_worker(
            conn, worker["id"], now
        ):
            booking = await live_work_repository.get_booking(conn, offer["shift_id"])
            items.append(
                WorkerLiveRequest(
                    booking_id=offer["shift_id"],
                    dispatch_id=offer["dispatch_id"],
                    job_title=booking["job_title"],
                    category_name=booking["category_name"],
                    business_name=booking["business_name"],
                    address_text=booking["address_text"] or "",
                    distance_km=round(float(offer["distance_km"]), 1)
                    if offer["distance_km"] is not None
                    else None,
                    reserved_minutes=booking["reserved_minutes"],
                    hourly_rate_minor=booking["hourly_rate_minor"],
                    worker_net_minor=booking["worker_net_minor"],
                    currency=booking["currency"],
                    expires_at=offer["expires_at"],
                    seconds_left=max(int((offer["expires_at"] - now).total_seconds()), 0),
                )
            )
    return items


async def accept(user: AuthenticatedUser, shift_id: UUID) -> WorkerLiveBooking:
    """First Worker wins: the shift row is locked and one seat is enforced by a unique index.
    Eligibility (offer, decline, distance, availability) is the shared live dispatcher's."""
    async with get_pool().acquire() as conn:
        if not await live_work_repository.is_live_work(conn, shift_id):
            raise live_work_core.not_found_error()
    detail = await live_dispatch_service.accept(user, shift_id)
    async with get_pool().acquire() as conn:
        return await _state(conn, detail.id)


async def decline(user: AuthenticatedUser, shift_id: UUID) -> None:
    await live_dispatch_service.decline(user, shift_id)


async def active(user: AuthenticatedUser) -> WorkerActiveLiveWork:
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        assignment_id = await live_work_repository.get_worker_active_assignment_id(
            conn, worker["id"]
        )
        if assignment_id is None:
            return WorkerActiveLiveWork(booking=None)
        return WorkerActiveLiveWork(booking=await _state(conn, assignment_id))


async def history(
    user: AuthenticatedUser, limit: int | None, offset: int
) -> list[WorkerLiveBooking]:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        ids = await live_work_repository.list_worker_assignment_ids(
            conn, worker["id"], page_limit, offset
        )
        return [await _state(conn, assignment_id) for assignment_id in ids]


async def get_booking(user: AuthenticatedUser, assignment_id: UUID) -> WorkerLiveBooking:
    async with get_pool().acquire() as conn:
        await _owned_assignment(conn, user, assignment_id, lock=False)
        return await _state(conn, assignment_id)


async def start_travel(user: AuthenticatedUser, assignment_id: UUID) -> WorkerLiveBooking:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _, ctx = await _owned_assignment(conn, user, assignment_id, lock=True)
            if ctx["status"] != ASG_CONFIRMED:
                raise live_work_core.state_error({"stage": ctx["status"]})
            await assignment_repository.start_travel(conn, assignment_id, now)
            await notify(
                conn,
                ctx["business_user_id"],
                KIND_WORKER_EN_ROUTE,
                "Worker is on the way",
                ctx["job_title"],
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id, "live_work": True},
            )
        return await _state(conn, assignment_id)


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if latitude == 0 and longitude == 0:
        raise bad_request(
            "location_invalid",
            "We couldn't read your location. Turn on location and try again.",
            {"fields": {"location": "Invalid location"}},
        )


async def update_location(
    user: AuthenticatedUser, assignment_id: UUID, body: LiveLocationUpdate
) -> WorkerLiveBooking:
    """Device location while assigned. Only shared with the Business of this booking."""
    _validate_coordinates(body.latitude, body.longitude)
    now = utc_now()
    async with get_pool().acquire() as conn:
        _, ctx = await _owned_assignment(conn, user, assignment_id, lock=False)
        if ctx["status"] not in ("confirmed", "en_route", "checked_in"):
            raise live_work_core.state_error({"stage": ctx["status"]})
        await profile_repository.upsert_worker_location(
            conn,
            ctx["worker_profile_id"],
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy_m=body.accuracy_m,
            recorded_at=now,
        )
        return await _state(conn, assignment_id)


async def start_work(
    user: AuthenticatedUser, assignment_id: UUID, body: LiveStartWork
) -> WorkerLiveBooking:
    """Arrival code + location check. Idempotent once started. Wrong codes are counted in a
    committed transaction (so the limit holds), then the error is raised."""
    _validate_coordinates(body.latitude, body.longitude)
    settings = load_settings()
    now = utc_now()
    failure: ApiError | None = None
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _, ctx = await _owned_assignment(conn, user, assignment_id, lock=True)
            if ctx["status"] == ASG_CHECKED_IN:
                return await build_worker_state(conn, ctx, now)
            if ctx["status"] not in ("confirmed", "en_route"):
                raise live_work_core.state_error({"stage": ctx["status"]})
            code = await live_work_repository.lock_arrival_code(conn, assignment_id)
            if code is None:
                raise live_work_core.state_error()
            if code["locked_at"] is not None:
                raise conflict(
                    "arrival_code_locked",
                    "Too many wrong codes. Ask the Business to issue a new arrival code.",
                )
            if code["expires_at"] <= now:
                raise conflict(
                    "arrival_code_expired",
                    "This arrival code has expired. Ask the Business to issue a new one.",
                )
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
                    "You need to be at the Work Location to start work.",
                    {"distance_m": distance_m, "allowed_m": settings.check_in_radius_m},
                )
            entered = body.arrival_code.strip().upper()
            if not hmac.compare_digest(entered.encode(), code["code"].upper().encode()):
                row = await live_work_repository.record_failed_attempt(
                    conn, assignment_id, max_attempts=settings.live_arrival_max_attempts, now=now
                )
                left = max(settings.live_arrival_max_attempts - row["failed_attempts"], 0)
                failure = (
                    conflict(
                        "arrival_code_locked",
                        "Too many wrong codes. Ask the Business to issue a new arrival code.",
                    )
                    if row["locked_at"] is not None
                    else bad_request(
                        "arrival_code_invalid",
                        "That arrival code is incorrect.",
                        {"attempts_left": left, "fields": {"arrival_code": "Incorrect code"}},
                    )
                )
            else:
                pricing = await live_work_repository.get_booking_pricing(conn, ctx["shift_id"])
                shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
                await live_work_repository.set_arrival_verified(conn, assignment_id, now)
                await attendance_repository.insert_check_in(
                    conn,
                    assignment_id,
                    now=now,
                    latitude=body.latitude,
                    longitude=body.longitude,
                    distance_m=distance_m,
                )
                await live_work_repository.set_assignment_started(conn, assignment_id)
                await profile_repository.upsert_worker_location(
                    conn,
                    ctx["worker_profile_id"],
                    latitude=body.latitude,
                    longitude=body.longitude,
                    accuracy_m=body.accuracy_m,
                    recorded_at=now,
                )
                await live_work_repository.set_shift_window(
                    conn, shift["id"], now, now + timedelta(minutes=pricing["reserved_minutes"])
                )
                if shift["status"] == SHIFT_FILLED:
                    await shift_repository.set_status(
                        conn,
                        shift["id"],
                        from_status=SHIFT_FILLED,
                        to_status=SHIFT_IN_PROGRESS,
                        now=now,
                        actor_user_id=user.user_id,
                        reason="live_work_started",
                    )
                await notify(
                    conn,
                    ctx["business_user_id"],
                    KIND_WORKER_CHECKED_IN,
                    "Work started",
                    f"{ctx['job_title']} · arrival code verified",
                    {
                        "shift_id": ctx["shift_id"],
                        "assignment_id": assignment_id,
                        "live_work": True,
                    },
                )
        if failure is not None:
            raise failure
        return await _state(conn, assignment_id)


async def complete(user: AuthenticatedUser, assignment_id: UUID) -> WorkerLiveBooking:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _, ctx = await _owned_assignment(conn, user, assignment_id, lock=True)
            if ctx["status"] in ("checked_out", "approved"):
                return await build_worker_state(conn, ctx, now)
            shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
            pricing = await live_work_repository.get_booking_pricing(conn, ctx["shift_id"])
            await live_work_core.complete_booking(
                conn,
                shift=shift,
                pricing=pricing,
                assignment=ctx,
                ended_by="worker",
                actor_user_id=user.user_id,
                now=now,
            )
        return await _state(conn, assignment_id)


async def cancel_preview(user: AuthenticatedUser, assignment_id: UUID) -> LiveCancelPreview:
    async with get_pool().acquire() as conn:
        _, ctx = await _owned_assignment(conn, user, assignment_id, lock=False)
        pricing = await live_work_repository.get_booking_pricing(conn, ctx["shift_id"])
        plan, _ = await live_work_core.worker_cancel_plan(conn, pricing, ctx, utc_now())
    return cancel_preview_view(plan, pricing["currency"])


async def cancel(
    user: AuthenticatedUser, assignment_id: UUID, body: LiveCancelRequest
) -> WorkerLiveBooking:
    now = utc_now()
    refund_ids: list[UUID | None] = []
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _, ctx = await _owned_assignment(conn, user, assignment_id, lock=True)
            if ctx["status"] == "cancelled":
                return await build_worker_state(conn, ctx, now)
            shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
            pricing = await live_work_repository.get_booking_pricing(conn, ctx["shift_id"])
            plan, worked = await live_work_core.worker_cancel_plan(conn, pricing, ctx, now)
            if plan.stage == "during_work":
                refund_ids = await live_work_core.worker_walk_off(
                    conn,
                    shift=shift,
                    pricing=pricing,
                    assignment=ctx,
                    plan=plan,
                    worked=worked,
                    actor_user_id=user.user_id,
                    now=now,
                )
            else:
                await assignment_repository.cancel_assignment(
                    conn,
                    assignment_id,
                    now=now,
                    actor_user_id=user.user_id,
                    reason=cancel_reason("worker", body.reason),
                    late=plan.quote.fee_minor > 0,  # type: ignore[union-attr]
                )
                await cancellation_service.apply_seat(
                    conn,
                    shift=shift,
                    assignment_id=assignment_id,
                    worker_profile_id=ctx["worker_profile_id"],
                    worker_user_id=ctx["worker_user_id"],
                    quote=plan.quote,  # type: ignore[arg-type]
                    actor_user_id=user.user_id,
                    now=now,
                    seat_reopens=True,
                )
                await live_work_core.restart_search(
                    conn, shift, pricing, now, user.user_id, "worker_cancelled_reassign"
                )
                await live_work_core.notify_cancelled(
                    conn,
                    ctx["business_user_id"],
                    "Your Worker cancelled",
                    f"{shift['job_title']} · we're finding another Worker.",
                    {"shift_id": shift["id"], "live_work": True},
                )
        await live_refund_service.process_refunds(refund_ids)
        return await _state(conn, assignment_id)


async def answer_extension(
    user: AuthenticatedUser, assignment_id: UUID, extension_id: UUID, body: LiveExtensionAnswer
) -> WorkerLiveBooking:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _, ctx = await _owned_assignment(conn, user, assignment_id, lock=True)
            ext = await live_work_repository.lock_extension(conn, extension_id)
            if ext is None or ext["assignment_id"] != assignment_id:
                raise not_found("extension_not_found", "Extension not found.")
            if ext["status"] != "requested" or ctx["status"] != ASG_CHECKED_IN:
                raise live_work_core.state_error({"extension_status": ext["status"]})
            data = {"shift_id": ctx["shift_id"], "assignment_id": assignment_id, "live_work": True}
            if body.accept:
                pricing = await live_work_repository.get_booking_pricing(conn, ctx["shift_id"])
                invoice_id = await live_work_billing.create_extension_invoice(
                    conn, pricing, ext, now
                )
                await live_work_repository.set_extension_invoice(conn, extension_id, invoice_id)
                await live_work_repository.set_extension_status(
                    conn, extension_id, "awaiting_payment", now
                )
                await notify(
                    conn,
                    ctx["business_user_id"],
                    KIND_EXTENSION_ANSWERED,
                    "Worker accepted the extension",
                    f"Pay to add +{ext['extra_minutes']} min to {ctx['job_title']}.",
                    {**data, "invoice_id": invoice_id},
                )
            else:
                await live_work_repository.set_extension_status(conn, extension_id, "declined", now)
                await notify(
                    conn,
                    ctx["business_user_id"],
                    KIND_EXTENSION_ANSWERED,
                    "Worker declined the extension",
                    ctx["job_title"],
                    data,
                )
        return await _state(conn, assignment_id)
