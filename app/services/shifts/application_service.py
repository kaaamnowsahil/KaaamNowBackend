"""Scheduled shifts: applying books the seat at once.

``select`` / ``reject`` / ``confirm`` / ``decline`` remain for older clients only."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_WORKER
from app.constants.notifications.notification_route_strings import (
    KIND_APPLICATION_CONFIRMED,
    KIND_APPLICATION_DECLINED,
    KIND_APPLICATION_REJECTED,
    KIND_APPLICATION_SELECTED,
    KIND_LIVE_FILLED,
)
from app.constants.profiles.profile_route_strings import MSG_WORKER_LOCATION_REQUIRED
from app.constants.shifts.shift_route_strings import (
    APP_APPLIED,
    APP_CONFIRMED,
    APP_DECLINED,
    APP_EXPIRED,
    APP_REJECTED,
    APP_SELECTED,
    APP_WITHDRAWN,
    MSG_ALREADY_BOOKED,
    MSG_APPLICATION_EXISTS,
    MSG_APPLICATION_NOT_FOUND,
    MSG_APPLICATION_STATE,
    MSG_APPLY_CLOSED,
    MSG_CONFIRM_EXPIRED,
    MSG_NOT_SCHEDULED_SHIFT,
    MSG_OVERLAPPING_SHIFT,
    MSG_SHIFT_BEYOND_MAX_DISTANCE,
    MSG_SHIFT_FULL,
    MSG_SHIFT_NOT_FOUND,
    MSG_SHIFT_NOT_RECRUITING,
    MSG_TOO_MANY_BOOKINGS,
    MSG_WORKER_UNAVAILABLE,
    SHIFT_FILLED,
    SHIFT_OPEN,
    SHIFT_SCHEDULED,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.pagination import clamp_page_limit
from app.repositories.profiles import profile_repository
from app.repositories.shifts import application_repository, assignment_repository, shift_repository
from app.schemas.shifts.application_schemas import (
    ApplicantList,
    ApplicationCreate,
    ApplicationResponse,
    BusinessApplicantPage,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.catalog import catalog_service
from app.services.notifications.notification_service import notify, notify_many
from app.services.profiles.profile_lookup import (
    business_scope,
    ensure_worker_can_work,
    require_worker_profile,
    worker_home_point,
)
from app.services.shifts.domain.shift_mappers import applicant_item, business_applicant_item
from app.services.users import terms_service
from app.utils.clock import utc_now
from app.utils.geo import haversine_km

_CLOSED_STATUSES = [APP_REJECTED, APP_DECLINED, APP_WITHDRAWN, APP_EXPIRED]
_WORKER_LEFT_STATUSES = [APP_WITHDRAWN, APP_DECLINED]


async def _application_response(
    conn: asyncpg.Connection, application_id: UUID
) -> ApplicationResponse:
    row = await application_repository.get_application(conn, application_id)
    return ApplicationResponse.model_validate(dict(row))


async def _lock_for_worker(
    conn: asyncpg.Connection, application_id: UUID, worker_profile_id: UUID
) -> asyncpg.Record:
    app_row = await application_repository.lock_application(conn, application_id)
    if app_row is None or app_row["worker_profile_id"] != worker_profile_id:
        raise not_found("application_not_found", MSG_APPLICATION_NOT_FOUND)
    return app_row


async def _lock_for_business(
    conn: asyncpg.Connection, application_id: UUID, scope: list[UUID]
) -> asyncpg.Record:
    app_row = await application_repository.lock_application(conn, application_id)
    if app_row is None or app_row["business_profile_id"] not in scope:
        raise not_found("application_not_found", MSG_APPLICATION_NOT_FOUND)
    return app_row


async def _open_scheduled_shift(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record:
    shift = await shift_repository.lock_shift(conn, shift_id)
    if shift is None or shift["status"] == "draft":
        raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
    if shift["shift_type"] != SHIFT_SCHEDULED:
        raise bad_request("not_scheduled_shift", MSG_NOT_SCHEDULED_SHIFT)
    if shift["status"] != SHIFT_OPEN or shift["starts_at"] <= utc_now():
        raise conflict("shift_not_recruiting", MSG_SHIFT_NOT_RECRUITING)
    return shift


async def apply(
    user: AuthenticatedUser, shift_id: UUID, body: ApplicationCreate
) -> ApplicationResponse:
    """Applying books the seat straight away: no Business / Work selection, no confirm step."""
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            ensure_worker_can_work(worker)
            await terms_service.require_accepted(conn, user.user_id, ROLE_WORKER)
            shift = await _open_scheduled_shift(conn, shift_id)
            business = await profile_repository.get_business_profile(
                conn, shift["business_profile_id"]
            )
            if business["user_id"] == user.user_id:
                raise conflict("shift_not_recruiting", MSG_SHIFT_NOT_RECRUITING)
            closes_hours = settings.apply_closes_hours_before
            if shift["starts_at"] - timedelta(hours=closes_hours) <= now:
                raise conflict("apply_closed", MSG_APPLY_CLOSED.format(hours=closes_hours))
            seats = await shift_repository.count_seats(conn, shift_id)
            if seats >= shift["workers_required"]:
                raise conflict("shift_full", MSG_SHIFT_FULL)
            if await shift_repository.worker_has_overlap(
                conn,
                worker["id"],
                starts_at=shift["starts_at"],
                ends_at=shift["ends_at"],
                exclude_shift_id=shift["id"],
            ):
                raise conflict("overlapping_shift", MSG_OVERLAPPING_SHIFT)
            max_bookings = settings.max_upcoming_bookings_per_worker
            if (
                await shift_repository.count_worker_upcoming_bookings(conn, worker["id"], now)
                >= max_bookings
            ):
                raise conflict(
                    "too_many_bookings", MSG_TOO_MANY_BOOKINGS.format(count=max_bookings)
                )
            if body.latitude is not None and body.longitude is not None:
                lat, lng = body.latitude, body.longitude
            else:
                lat, lng = await worker_home_point(conn, worker)
            if lat is None or lng is None:
                raise bad_request("location_required", MSG_WORKER_LOCATION_REQUIRED)
            distance = haversine_km(lat, lng, shift["latitude"], shift["longitude"])
            max_km = (await catalog_service.search_radii(conn)).worker_max_shift_km
            if distance > max_km:
                raise bad_request("too_far", MSG_SHIFT_BEYOND_MAX_DISTANCE.format(km=max_km))
            row = await application_repository.upsert_application(
                conn,
                shift_id=shift_id,
                worker_profile_id=worker["id"],
                distance_km=distance,
                cover_note=body.cover_note,
                latitude=lat,
                longitude=lng,
            )
            if row is None:
                raise conflict("application_exists", MSG_APPLICATION_EXISTS)
            await _book_selected(conn, worker, row["id"], shift, seats, now)
            return await _application_response(conn, row["id"])


async def withdraw(user: AuthenticatedUser, application_id: UUID) -> ApplicationResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            app_row = await _lock_for_worker(conn, application_id, worker["id"])
            if app_row["status"] not in (APP_APPLIED, APP_SELECTED):
                raise conflict("application_state", MSG_APPLICATION_STATE)
            await application_repository.set_response(
                conn, application_id, status=APP_WITHDRAWN, now=now
            )
            return await _application_response(conn, application_id)


async def list_applicants(
    user: AuthenticatedUser, shift_id: UUID, statuses: list[str] | None
) -> ApplicantList:
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id)
        shift = await shift_repository.get_business_shift(conn, shift_id, scope)
        if shift is None:
            raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
        rows = await application_repository.list_applicants(conn, shift_id, statuses or None)
    return ApplicantList(
        shift_id=shift_id,
        workers_required=shift["workers_required"],
        booked_count=shift["booked_count"],
        items=[applicant_item(r) for r in rows],
    )


async def list_business_applicants(
    user: AuthenticatedUser,
    status: str,
    business_profile_id: UUID | None,
    limit: int | None,
    offset: int,
) -> BusinessApplicantPage:
    """Applicants across every shift the caller owns, for one application status."""
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id, business_profile_id)
        rows = await application_repository.list_business_applicants(
            conn,
            scope,
            _CLOSED_STATUSES
            if status == APP_REJECTED
            else _WORKER_LEFT_STATUSES
            if status == APP_WITHDRAWN
            else [status],
            limit=page_limit,
            offset=offset,
        )
    return BusinessApplicantPage(
        status=status,
        items=[business_applicant_item(r) for r in rows],
        limit=page_limit,
        offset=offset,
    )


async def select(user: AuthenticatedUser, application_id: UUID) -> ApplicationResponse:
    """Offer a seat. Selected + booked may not exceed workers_required."""
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            scope = await business_scope(conn, user.user_id)
            app_row = await _lock_for_business(conn, application_id, scope)
            shift = await _open_scheduled_shift(conn, app_row["shift_id"])
            business = await profile_repository.get_business_profile(
                conn, shift["business_profile_id"]
            )
            if app_row["status"] != APP_APPLIED:
                raise conflict("application_state", MSG_APPLICATION_STATE)
            if await shift_repository.worker_has_overlap(
                conn,
                app_row["worker_profile_id"],
                starts_at=shift["starts_at"],
                ends_at=shift["ends_at"],
                exclude_shift_id=shift["id"],
            ):
                raise conflict("worker_unavailable", MSG_WORKER_UNAVAILABLE)
            seats = await shift_repository.count_seats(conn, shift["id"])
            pending = await application_repository.count_selected(conn, shift["id"])
            if seats + pending >= shift["workers_required"]:
                raise conflict("shift_full", MSG_SHIFT_FULL)
            confirm_by = min(
                now + timedelta(hours=settings.selection_confirm_hours), shift["starts_at"]
            )
            await application_repository.set_decision(
                conn, application_id, status=APP_SELECTED, now=now, confirm_by=confirm_by
            )
            worker = await profile_repository.get_worker_profile(conn, app_row["worker_profile_id"])
            await notify(
                conn,
                worker["user_id"],
                KIND_APPLICATION_SELECTED,
                "You've been selected!",
                f"{business['business_name']} · {shift['job_title']}. Confirm to lock it in.",
                {
                    "shift_id": shift["id"],
                    "application_id": application_id,
                    "confirm_by": confirm_by.isoformat(),
                },
            )
            return await _application_response(conn, application_id)


async def reject(user: AuthenticatedUser, application_id: UUID) -> ApplicationResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            scope = await business_scope(conn, user.user_id)
            app_row = await _lock_for_business(conn, application_id, scope)
            if app_row["status"] not in (APP_APPLIED, APP_SELECTED):
                raise conflict("application_state", MSG_APPLICATION_STATE)
            await application_repository.set_decision(
                conn, application_id, status=APP_REJECTED, now=now, confirm_by=None
            )
            worker = await profile_repository.get_worker_profile(conn, app_row["worker_profile_id"])
            await notify(
                conn,
                worker["user_id"],
                KIND_APPLICATION_REJECTED,
                "Application update",
                "The hirer went with other applicants this time.",
                {"shift_id": app_row["shift_id"], "application_id": application_id},
            )
            return await _application_response(conn, application_id)


async def _book_selected(
    conn: asyncpg.Connection,
    worker: asyncpg.Record,
    application_id: UUID,
    shift: asyncpg.Record,
    seats: int,
    now: datetime,
) -> None:
    try:
        async with conn.transaction():
            assignment_id = await assignment_repository.insert_assignment(
                conn,
                shift_id=shift["id"],
                worker_profile_id=worker["id"],
                source=SHIFT_SCHEDULED,
                dispatch_id=None,
                application_id=application_id,
                hourly_rate_minor=shift["hourly_rate_minor"],
                now=now,
            )
    except asyncpg.UniqueViolationError:
        raise conflict("already_booked", MSG_ALREADY_BOOKED) from None
    await application_repository.set_response(conn, application_id, status=APP_CONFIRMED, now=now)
    business = await profile_repository.get_business_profile(conn, shift["business_profile_id"])
    await notify(
        conn,
        business["user_id"],
        KIND_APPLICATION_CONFIRMED,
        f"{worker['full_name'] or 'A worker'} booked",
        f"{shift['job_title']} · {seats + 1} of {shift['workers_required']} booked",
        {"shift_id": shift["id"], "assignment_id": assignment_id},
    )
    if seats + 1 < shift["workers_required"]:
        return
    await shift_repository.set_status(
        conn,
        shift["id"],
        from_status=SHIFT_OPEN,
        to_status=SHIFT_FILLED,
        now=now,
        reason="all_seats_confirmed",
    )
    rejected = await application_repository.reject_remaining_applied(conn, shift["id"], now)
    await notify_many(
        conn,
        await assignment_repository.user_ids_for_worker_profiles(conn, rejected),
        KIND_APPLICATION_REJECTED,
        "Shift filled",
        f"{shift['job_title']} has been filled.",
        {"shift_id": shift["id"]},
    )
    await notify(
        conn,
        business["user_id"],
        KIND_LIVE_FILLED,
        "Shift fully booked",
        f"All workers booked for {shift['job_title']}.",
        {"shift_id": shift["id"]},
    )


async def confirm(user: AuthenticatedUser, application_id: UUID) -> ApplicationResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            ensure_worker_can_work(worker)
            app_row = await _lock_for_worker(conn, application_id, worker["id"])
            if app_row["status"] != APP_SELECTED:
                raise conflict("application_state", MSG_APPLICATION_STATE)
            if app_row["confirm_by"] is not None and app_row["confirm_by"] <= now:
                raise conflict("confirm_expired", MSG_CONFIRM_EXPIRED)
            shift = await _open_scheduled_shift(conn, app_row["shift_id"])
            seats = await shift_repository.count_seats(conn, shift["id"])
            if seats >= shift["workers_required"]:
                raise conflict("shift_full", MSG_SHIFT_FULL)
            if await shift_repository.worker_has_overlap(
                conn,
                worker["id"],
                starts_at=shift["starts_at"],
                ends_at=shift["ends_at"],
                exclude_shift_id=shift["id"],
            ):
                raise conflict("overlapping_shift", MSG_OVERLAPPING_SHIFT)
            await _book_selected(conn, worker, application_id, shift, seats, now)
            return await _application_response(conn, application_id)


async def decline(user: AuthenticatedUser, application_id: UUID) -> ApplicationResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            app_row = await _lock_for_worker(conn, application_id, worker["id"])
            if app_row["status"] != APP_SELECTED:
                raise conflict("application_state", MSG_APPLICATION_STATE)
            await application_repository.set_response(
                conn, application_id, status=APP_DECLINED, now=now
            )
            business = await profile_repository.get_business_profile(
                conn, app_row["business_profile_id"]
            )
            await notify(
                conn,
                business["user_id"],
                KIND_APPLICATION_DECLINED,
                f"{worker['full_name'] or 'A worker'} declined",
                "Select another applicant to fill the spot.",
                {"shift_id": app_row["shift_id"], "application_id": application_id},
            )
            return await _application_response(conn, application_id)
