"""Business side of shifts: create, edit draft, publish, cancel, dashboard, live search."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_SHIFT_CANCELLED,
    KIND_SHIFT_NEARBY,
)
from app.constants.shifts.shift_route_strings import (
    APP_REJECTED,
    ASG_BOOKED_STATUSES,
    ASG_CHECKED_IN,
    CHECK_IN_CODE_LENGTH,
    MSG_CONVERT_NOT_ALLOWED,
    MSG_RETRY_NOT_ALLOWED,
    MSG_SHIFT_NOT_CANCELLABLE,
    MSG_SHIFT_NOT_DRAFT,
    MSG_SHIFT_NOT_FOUND,
    SCHEDULED_NOTIFY_BATCH_SIZE,
    SHIFT_CANCELLABLE_STATUSES,
    SHIFT_CANCELLED,
    SHIFT_DRAFT,
    SHIFT_EXPIRED,
    SHIFT_LIVE,
    SHIFT_OPEN,
    SHIFT_SCHEDULED,
    SHIFT_SEARCHING,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.pagination import clamp_page_limit
from app.repositories.profiles import profile_repository
from app.repositories.shifts import (
    application_repository,
    assignment_repository,
    dispatch_repository,
    shift_repository,
)
from app.schemas.shifts.shift_schemas import (
    ConvertToScheduledRequest,
    DashboardResponse,
    DashboardSummary,
    LiveSearchStatus,
    ShiftCancelRequest,
    ShiftCostEstimate,
    ShiftCreate,
    ShiftEstimateRequest,
    ShiftPage,
    ShiftPatch,
    ShiftResponse,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.catalog import catalog_service
from app.services.notifications.notification_service import notify_many
from app.services.profiles.profile_lookup import (
    require_business_profile,
    require_postable_business,
)
from app.services.shifts import live_dispatch_service
from app.services.shifts.domain.shift_mappers import (
    live_search_state,
    shift_list_item,
    shift_response,
)
from app.services.shifts.domain.shift_rules import (
    estimate_cost,
    is_late_cancellation,
    paid_minutes,
    resolve_window,
    validate_window,
)
from app.utils.clock import minutes_between, utc_now
from app.utils.geo import bounding_box_deltas
from app.utils.references import new_numeric_code

# --- helpers ---------------------------------------------------------------------------


async def _estimate_for(conn: asyncpg.Connection, row: asyncpg.Record) -> ShiftCostEstimate:
    if row["fee_percentage"] is not None:
        pct = Decimal(row["fee_percentage"])
    else:
        pct = Decimal((await catalog_service.require_active_fee_policy(conn))["percentage"])
    return estimate_cost(
        hourly_rate_minor=row["hourly_rate_minor"],
        workers_required=row["workers_required"],
        minutes_per_worker=paid_minutes(row["starts_at"], row["ends_at"], row["break_minutes"]),
        fee_percentage=pct,
        currency=row["currency"],
    )


async def _load_owned(
    conn: asyncpg.Connection, business_profile_id: UUID, shift_id: UUID
) -> asyncpg.Record:
    row = await shift_repository.get_business_shift(conn, shift_id, business_profile_id)
    if row is None:
        raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
    return row


async def _lock_owned(
    conn: asyncpg.Connection, business_profile_id: UUID, shift_id: UUID
) -> asyncpg.Record:
    row = await shift_repository.lock_shift(conn, shift_id)
    if row is None or row["business_profile_id"] != business_profile_id:
        raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
    return row


async def build_shift_response(
    conn: asyncpg.Connection, business_profile_id: UUID, shift_id: UUID
) -> ShiftResponse:
    row = await _load_owned(conn, business_profile_id, shift_id)
    return shift_response(row, await _estimate_for(conn, row), utc_now())


def _merged_values(
    base: dict[str, Any], body: ShiftCreate | ShiftPatch, business: asyncpg.Record
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    values = dict(base)
    for key in (
        "job_title",
        "responsibilities",
        "requirements",
        "workers_required",
        "hourly_rate_minor",
        "break_minutes",
        "workplace_name",
        "address_text",
        "latitude",
        "longitude",
        "arrival_instructions",
        "site_contact_name",
        "cancellation_cutoff_hours",
    ):
        if key in patch and patch[key] is not None:
            values[key] = patch[key]
    if not values.get("address_text"):
        values["address_text"] = business["address_text"] or business["locality"]
    if values.get("latitude") is None:
        values["latitude"], values["longitude"] = business["latitude"], business["longitude"]
    if not values.get("workplace_name"):
        values["workplace_name"] = business["business_name"]
    return values


async def _notify_nearby_scheduled(conn: asyncpg.Connection, shift: asyncpg.Record) -> None:
    settings = load_settings()
    radius = settings.scheduled_notify_radius_km
    lat_delta, lng_delta = bounding_box_deltas(shift["latitude"], radius)
    business = await profile_repository.get_business_profile(conn, shift["business_profile_id"])
    user_ids = await dispatch_repository.list_workers_near_scheduled(
        conn,
        shift=shift,
        radius_km=radius,
        require_verified=settings.require_verified_workers,
        lat_delta=lat_delta,
        lng_delta=lng_delta,
        business_user_id=business["user_id"],
        limit=SCHEDULED_NOTIFY_BATCH_SIZE,
    )
    await notify_many(
        conn,
        user_ids,
        KIND_SHIFT_NEARBY,
        f"New shift near you: {shift['job_title']}",
        f"{business['business_name']} · apply now",
        {"shift_id": shift["id"]},
    )


async def _publish_locked(
    conn: asyncpg.Connection, shift: asyncpg.Record, actor: AuthenticatedUser, now: datetime
) -> None:
    settings = load_settings()
    if shift["status"] != SHIFT_DRAFT:
        raise conflict("shift_not_draft", MSG_SHIFT_NOT_DRAFT)
    starts_at, ends_at = shift["starts_at"], shift["ends_at"]
    if shift["shift_type"] == SHIFT_LIVE:
        duration = ends_at - starts_at
        starts_at, ends_at = now, now + duration
        await shift_repository.set_window(conn, shift["id"], starts_at=starts_at, ends_at=ends_at)
    validate_window(
        shift_type=shift["shift_type"],
        starts_at=starts_at,
        ends_at=ends_at,
        break_minutes=shift["break_minutes"],
        now=now,
    )
    policy = await catalog_service.require_active_fee_policy(conn)
    if shift["shift_type"] == SHIFT_LIVE:
        await shift_repository.publish_live(
            conn,
            shift["id"],
            now=now,
            fee_policy_version=policy["version"],
            fee_percentage=policy["percentage"],
            radius_km=settings.live_initial_radius_km,
            max_radius_km=settings.live_max_radius_km,
            expires_at=now + timedelta(seconds=settings.live_search_timeout_seconds),
        )
        await shift_repository.record_history(
            conn, shift["id"], SHIFT_DRAFT, SHIFT_SEARCHING, actor.user_id, "published"
        )
        await live_dispatch_service.dispatch_round(
            conn, await shift_repository.lock_shift(conn, shift["id"]), now
        )
    else:
        await shift_repository.publish_scheduled(
            conn,
            shift["id"],
            now=now,
            fee_policy_version=policy["version"],
            fee_percentage=policy["percentage"],
        )
        await shift_repository.record_history(
            conn, shift["id"], SHIFT_DRAFT, SHIFT_OPEN, actor.user_id, "published"
        )
        await _notify_nearby_scheduled(conn, await shift_repository.lock_shift(conn, shift["id"]))


# --- public API ------------------------------------------------------------------------


async def estimate(body: ShiftEstimateRequest) -> ShiftCostEstimate:
    now = utc_now()
    starts_at, ends_at = resolve_window(
        shift_type=SHIFT_LIVE,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        duration_minutes=body.duration_minutes,
        now=now,
    )
    async with get_pool().acquire() as conn:
        policy = await catalog_service.require_active_fee_policy(conn)
    return estimate_cost(
        hourly_rate_minor=body.hourly_rate_minor,
        workers_required=body.workers_required,
        minutes_per_worker=paid_minutes(starts_at, ends_at, body.break_minutes),
        fee_percentage=Decimal(policy["percentage"]),
        currency=load_settings().default_currency,
    )


async def create_shift(user: AuthenticatedUser, body: ShiftCreate) -> ShiftResponse:
    settings = load_settings()
    now = utc_now()
    starts_at, ends_at = resolve_window(
        shift_type=body.shift_type,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        duration_minutes=body.duration_minutes,
        now=now,
    )
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_postable_business(conn, user.user_id)
            base = {
                "category_id": await catalog_service.resolve_category_id(conn, body.category_slug),
                "responsibilities": "",
                "requirements": "",
                "break_minutes": 0,
                "workplace_name": "",
                "address_text": "",
                "latitude": None,
                "longitude": None,
                "arrival_instructions": "",
                "site_contact_name": "",
                "cancellation_cutoff_hours": settings.default_cancellation_cutoff_hours,
                "starts_at": starts_at,
                "ends_at": ends_at,
            }
            values = _merged_values(base, body, business)
            validate_window(
                shift_type=body.shift_type,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=values["break_minutes"],
                now=now,
            )
            shift_id = await shift_repository.insert_shift(
                conn,
                business_profile_id=business["id"],
                shift_type=body.shift_type,
                currency=settings.default_currency,
                check_in_code=new_numeric_code(CHECK_IN_CODE_LENGTH),
                values=values,
            )
            if body.publish:
                await _publish_locked(
                    conn, await shift_repository.lock_shift(conn, shift_id), user, now
                )
            return await build_shift_response(conn, business["id"], shift_id)


async def update_draft(user: AuthenticatedUser, shift_id: UUID, body: ShiftPatch) -> ShiftResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_business_profile(conn, user.user_id)
            shift = await _lock_owned(conn, business["id"], shift_id)
            if shift["status"] != SHIFT_DRAFT:
                raise conflict("shift_not_draft", MSG_SHIFT_NOT_DRAFT)
            values = _merged_values({k: shift[k] for k in shift.keys()}, body, business)
            if body.category_slug:
                values["category_id"] = await catalog_service.resolve_category_id(
                    conn, body.category_slug
                )
            if body.starts_at or body.ends_at or body.duration_minutes:
                duration = body.duration_minutes or minutes_between(
                    shift["starts_at"], shift["ends_at"]
                )
                values["starts_at"], values["ends_at"] = resolve_window(
                    shift_type=shift["shift_type"],
                    starts_at=body.starts_at or shift["starts_at"],
                    ends_at=body.ends_at,
                    duration_minutes=duration,
                    now=now,
                )
            if shift["shift_type"] == SHIFT_SCHEDULED:
                validate_window(
                    shift_type=shift["shift_type"],
                    starts_at=values["starts_at"],
                    ends_at=values["ends_at"],
                    break_minutes=values["break_minutes"],
                    now=now,
                )
            await shift_repository.update_draft_shift(conn, shift_id, values)
            return await build_shift_response(conn, business["id"], shift_id)


async def publish(user: AuthenticatedUser, shift_id: UUID) -> ShiftResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_postable_business(conn, user.user_id)
            shift = await _lock_owned(conn, business["id"], shift_id)
            await _publish_locked(conn, shift, user, now)
            return await build_shift_response(conn, business["id"], shift_id)


async def cancel(
    user: AuthenticatedUser, shift_id: UUID, body: ShiftCancelRequest
) -> ShiftResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_business_profile(conn, user.user_id)
            shift = await _lock_owned(conn, business["id"], shift_id)
            if shift["status"] not in SHIFT_CANCELLABLE_STATUSES:
                raise conflict("shift_not_cancellable", MSG_SHIFT_NOT_CANCELLABLE)
            if await assignment_repository.count_in(conn, shift_id, [ASG_CHECKED_IN]):
                raise conflict("shift_not_cancellable", MSG_SHIFT_NOT_CANCELLABLE)
            late = is_late_cancellation(shift["starts_at"], shift["cancellation_cutoff_hours"], now)
            worker_ids = await assignment_repository.cancel_shift_assignments(
                conn,
                shift_id,
                now=now,
                actor_user_id=user.user_id,
                reason=body.reason or "shift_cancelled",
                late=late,
            )
            worker_ids += await dispatch_repository.withdraw_open_offers(conn, shift_id)
            worker_ids += await application_repository.close_open_applications(
                conn, shift_id, status=APP_REJECTED, now=now
            )
            await shift_repository.cancel_shift(conn, shift_id, now=now, reason=body.reason)
            await shift_repository.record_history(
                conn, shift_id, shift["status"], SHIFT_CANCELLED, user.user_id, body.reason
            )
            user_ids = await assignment_repository.user_ids_for_worker_profiles(
                conn, list(set(worker_ids))
            )
            await notify_many(
                conn,
                user_ids,
                KIND_SHIFT_CANCELLED,
                f"Shift cancelled: {shift['job_title']}",
                body.reason,
                {"shift_id": shift_id},
            )
            return await build_shift_response(conn, business["id"], shift_id)


async def convert_to_scheduled(
    user: AuthenticatedUser, shift_id: UUID, body: ConvertToScheduledRequest
) -> ShiftResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_business_profile(conn, user.user_id)
            shift = await _lock_owned(conn, business["id"], shift_id)
            seats = await shift_repository.count_seats(conn, shift_id)
            allowed = shift["shift_type"] == SHIFT_LIVE and (
                shift["status"] == SHIFT_EXPIRED
                or (shift["status"] == SHIFT_SEARCHING and seats == 0)
            )
            if not allowed:
                raise conflict("convert_not_allowed", MSG_CONVERT_NOT_ALLOWED)
            starts_at, ends_at = resolve_window(
                shift_type=SHIFT_SCHEDULED,
                starts_at=body.starts_at,
                ends_at=body.ends_at,
                duration_minutes=body.duration_minutes
                or minutes_between(shift["starts_at"], shift["ends_at"]),
                now=now,
            )
            validate_window(
                shift_type=SHIFT_SCHEDULED,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=shift["break_minutes"],
                now=now,
            )
            await dispatch_repository.withdraw_open_offers(conn, shift_id)
            await shift_repository.convert_to_scheduled(
                conn, shift_id, starts_at=starts_at, ends_at=ends_at, now=now
            )
            await shift_repository.record_history(
                conn, shift_id, shift["status"], SHIFT_OPEN, user.user_id, "converted_to_scheduled"
            )
            await _notify_nearby_scheduled(conn, await shift_repository.lock_shift(conn, shift_id))
            return await build_shift_response(conn, business["id"], shift_id)


async def retry_live(user: AuthenticatedUser, shift_id: UUID) -> ShiftResponse:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            business = await require_business_profile(conn, user.user_id)
            shift = await _lock_owned(conn, business["id"], shift_id)
            if shift["shift_type"] != SHIFT_LIVE or shift["status"] != SHIFT_EXPIRED:
                raise conflict("retry_not_allowed", MSG_RETRY_NOT_ALLOWED)
            duration = shift["ends_at"] - shift["starts_at"]
            await shift_repository.set_window(conn, shift_id, starts_at=now, ends_at=now + duration)
            await dispatch_repository.delete_unanswered(conn, shift_id)
            await shift_repository.publish_live(
                conn,
                shift_id,
                now=now,
                fee_policy_version=shift["fee_policy_version"],
                fee_percentage=shift["fee_percentage"],
                radius_km=settings.live_initial_radius_km,
                max_radius_km=settings.live_max_radius_km,
                expires_at=now + timedelta(seconds=settings.live_search_timeout_seconds),
            )
            await shift_repository.record_history(
                conn, shift_id, SHIFT_EXPIRED, SHIFT_SEARCHING, user.user_id, "retry_live"
            )
            await live_dispatch_service.dispatch_round(
                conn, await shift_repository.lock_shift(conn, shift_id), now
            )
            return await build_shift_response(conn, business["id"], shift_id)


async def get_shift(user: AuthenticatedUser, shift_id: UUID) -> ShiftResponse:
    async with get_pool().acquire() as conn:
        business = await require_business_profile(conn, user.user_id)
        return await build_shift_response(conn, business["id"], shift_id)


async def list_shifts(
    user: AuthenticatedUser,
    *,
    shift_type: str | None,
    statuses: list[str] | None,
    limit: int | None,
    offset: int,
) -> ShiftPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        business = await require_business_profile(conn, user.user_id)
        rows = await shift_repository.list_business_shifts(
            conn,
            business["id"],
            shift_type=shift_type,
            statuses=statuses or None,
            limit=page_limit,
            offset=offset,
        )
    return ShiftPage(items=[shift_list_item(r) for r in rows], limit=page_limit, offset=offset)


async def dashboard(user: AuthenticatedUser, tab: str) -> DashboardResponse:
    async with get_pool().acquire() as conn:
        business = await require_business_profile(conn, user.user_id)
        summary = await shift_repository.dashboard_summary(conn, business["id"])
        rows = await shift_repository.list_dashboard_shifts(conn, business["id"], tab, utc_now())
    return DashboardResponse(
        tab=tab,  # type: ignore[arg-type]
        summary=DashboardSummary.model_validate(dict(summary)),
        shifts=[shift_list_item(r) for r in rows],
    )


async def live_search_status(user: AuthenticatedUser, shift_id: UUID) -> LiveSearchStatus:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        business = await require_business_profile(conn, user.user_id)
        row = await _load_owned(conn, business["id"], shift_id)
        radius = row["max_search_radius_km"] or settings.live_max_radius_km
        lat_delta, lng_delta = bounding_box_deltas(row["latitude"], radius)
        nearby = await shift_repository.count_active_workers_near(
            conn,
            latitude=row["latitude"],
            longitude=row["longitude"],
            radius_km=radius,
            require_verified=settings.require_verified_workers,
            fresh_since=now - timedelta(seconds=settings.location_freshness_seconds),
            lat_delta=lat_delta,
            lng_delta=lng_delta,
        )
        notified = await dispatch_repository.count_dispatches(conn, shift_id)
        booked = await assignment_repository.count_in(
            conn, shift_id, [*ASG_BOOKED_STATUSES, ASG_CHECKED_IN]
        )
    is_live = row["shift_type"] == SHIFT_LIVE
    return LiveSearchStatus(
        shift_id=shift_id,
        status=row["status"],
        workers_required=row["workers_required"],
        accepted_count=booked,
        notified_count=notified,
        active_workers_nearby=nearby,
        live_search=live_search_state(row, now),
        can_convert_to_scheduled=is_live
        and (row["status"] == SHIFT_EXPIRED or (row["status"] == SHIFT_SEARCHING and booked == 0)),
        can_retry=is_live and row["status"] == SHIFT_EXPIRED,
    )
