"""Worker discovery: "Shifts near you", shift detail, "My shifts"."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.profiles.profile_route_strings import MSG_WORKER_LOCATION_REQUIRED
from app.constants.shifts.shift_route_strings import (
    APP_APPLIED,
    APP_CONFIRMED,
    APP_DECLINED,
    APP_EXPIRED,
    APP_REJECTED,
    APP_SELECTED,
    APP_WITHDRAWN,
    ASG_APPROVED,
    ASG_CANCELLED,
    ASG_CHECKED_IN,
    ASG_CHECKED_OUT,
    ASG_CONFIRMED,
    ASG_EN_ROUTE,
    DISPATCH_WITHDRAWN,
    MSG_SHIFT_NOT_FOUND,
    SHIFT_LIVE,
    SHIFT_OPEN,
    SHIFT_SEARCHING,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, not_found
from app.pagination import clamp_page_limit
from app.repositories.shifts import shift_repository
from app.schemas.shifts.shift_schemas import (
    FeedPage,
    MyShiftItem,
    MyShiftsPage,
    WorkerShiftDetail,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.catalog import catalog_service
from app.services.profiles.profile_lookup import require_worker_profile, worker_home_point
from app.services.shifts.domain.shift_mappers import worker_shift_card, worker_shift_detail
from app.utils.clock import utc_now
from app.utils.geo import bounding_box_deltas

_ASSIGNMENT_TABS: dict[str, tuple[list[str], bool]] = {
    "upcoming": ([ASG_CONFIRMED, ASG_EN_ROUTE], False),
    "active": ([ASG_CHECKED_IN], False),
    "completed": ([ASG_CHECKED_OUT, ASG_APPROVED], True),
}
_APPLICATION_TAB_STATUSES = [
    APP_APPLIED,
    APP_SELECTED,
    APP_REJECTED,
    APP_DECLINED,
    APP_WITHDRAWN,
    APP_EXPIRED,
]


async def _worker_point(
    conn: asyncpg.Connection,
    worker: asyncpg.Record,
    latitude: float | None,
    longitude: float | None,
) -> tuple[float | None, float | None]:
    """A client-sent point is the device's current GPS for this request only (not saved)."""
    if latitude is not None and longitude is not None:
        return latitude, longitude
    return await worker_home_point(conn, worker)


async def feed(
    user: AuthenticatedUser,
    *,
    latitude: float | None,
    longitude: float | None,
    radius_km: float | None,
    shift_type: str | None,
    category_slug: str | None,
    business_type_slugs: list[str] | None,
    query: str | None,
    sort: str,
    limit: int | None,
    offset: int,
) -> FeedPage:
    settings = load_settings()
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        lat, lng = await _worker_point(conn, worker, latitude, longitude)
        if lat is None or lng is None:
            raise bad_request("location_required", MSG_WORKER_LOCATION_REQUIRED)
        now = utc_now()
        if worker["feed_limited_until"] is not None and worker["feed_limited_until"] > now:
            page_limit = max(min(page_limit, settings.limited_feed_size - offset), 0)
            if page_limit == 0:
                return FeedPage(items=[], limit=0, offset=offset)
        radii = await catalog_service.search_radii(conn)
        radius = min(radius_km or radii.feed_km, radii.worker_max_shift_km)
        lat_delta, lng_delta = bounding_box_deltas(lat, radius)
        rows = await shift_repository.list_feed(
            conn,
            worker_profile_id=worker["id"],
            own_user_id=user.user_id,
            latitude=lat,
            longitude=lng,
            radius_km=radius,
            lat_delta=lat_delta,
            lng_delta=lng_delta,
            shift_type=shift_type,
            category_slug=category_slug,
            business_type_slugs=business_type_slugs,
            query=(query or "").strip() or None,
            sort=sort,
            now=now,
            limit=page_limit,
            offset=offset,
        )
    return FeedPage(items=[worker_shift_card(r) for r in rows], limit=page_limit, offset=offset)


async def get_shift(
    user: AuthenticatedUser,
    shift_id: UUID,
    latitude: float | None = None,
    longitude: float | None = None,
) -> WorkerShiftDetail:
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        lat, lng = await _worker_point(conn, worker, latitude, longitude)
        row = await shift_repository.get_worker_shift(
            conn, shift_id, worker_profile_id=worker["id"], latitude=lat, longitude=lng
        )
        if row is None or (row["status"] == "draft"):
            raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
        has_conflict = row["my_assignment_status"] in (None, ASG_CANCELLED) and (
            await shift_repository.worker_has_overlap(
                conn,
                worker["id"],
                starts_at=row["starts_at"],
                ends_at=row["ends_at"],
                exclude_shift_id=row["id"],
            )
        )
    reason = _reapply_block_reason(row, has_conflict, utc_now())
    return worker_shift_detail(row).model_copy(
        update={
            "has_time_conflict": has_conflict,
            "can_reapply": _left_shift(row) and reason is None,
            "reapply_block_reason": reason if _left_shift(row) else None,
        }
    )


def _left_shift(row: asyncpg.Record) -> bool:
    """The worker withdrew, cancelled their booking, or was removed (no active response)."""
    if row["my_assignment_status"] not in (None, ASG_CANCELLED):
        return False
    if row["shift_type"] == SHIFT_LIVE:
        return row["my_assignment_status"] == ASG_CANCELLED
    return row["my_application_status"] in (APP_WITHDRAWN, APP_CONFIRMED)


def _reapply_block_reason(row: asyncpg.Record, has_conflict: bool, now: datetime) -> str | None:
    """Mirrors the apply / live accept checks so the button never offers a refused action."""
    if row["shift_type"] == SHIFT_LIVE:
        if row["my_dispatch_status"] != DISPATCH_WITHDRAWN:
            return "business_cancelled"
        if row["my_reaccept_count"]:
            return "reapply_limit"
        searching = row["status"] == SHIFT_SEARCHING and (
            row["search_expires_at"] is not None and row["search_expires_at"] > now
        )
        if not searching:
            return "not_recruiting"
    else:
        if row["my_application_status"] != APP_WITHDRAWN:
            return "business_cancelled"
        if row["my_reapply_count"]:
            return "reapply_limit"
        if row["status"] not in (SHIFT_SEARCHING, SHIFT_OPEN):
            return "not_recruiting"
        closes = timedelta(hours=load_settings().apply_closes_hours_before)
        if row["starts_at"] - closes <= now:
            return "apply_closed"
    if row["booked_count"] >= row["workers_required"]:
        return "shift_full"
    if has_conflict:
        return "overlapping_shift"
    return None


async def my_shifts(
    user: AuthenticatedUser,
    tab: str,
    limit: int | None,
    offset: int,
    latitude: float | None = None,
    longitude: float | None = None,
) -> MyShiftsPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        lat, lng = await _worker_point(conn, worker, latitude, longitude)
        if tab in _ASSIGNMENT_TABS:
            statuses, newest_first = _ASSIGNMENT_TABS[tab]
            rows = await shift_repository.list_my_assignment_shifts(
                conn,
                worker["id"],
                statuses=statuses,
                newest_first=newest_first,
                latitude=lat,
                longitude=lng,
                limit=page_limit,
                offset=offset,
            )
        else:
            rows = await shift_repository.list_my_application_shifts(
                conn,
                worker["id"],
                statuses=_APPLICATION_TAB_STATUSES,
                latitude=lat,
                longitude=lng,
                limit=page_limit,
                offset=offset,
            )
    items = [
        MyShiftItem(
            tab=tab,
            assignment_id=r["my_assignment_id"],
            assignment_status=r["my_assignment_status"],
            application_id=r["my_application_id"],
            application_status=r["my_application_status"],
            confirm_by=r["my_confirm_by"],
            applied_at=r["my_applied_at"],
            decided_at=r["my_decided_at"],
            responded_at=r["my_responded_at"],
            earned_minor=r["earned_minor"],
            shift=worker_shift_card(r),
        )
        for r in rows
    ]
    return MyShiftsPage(tab=tab, items=items, limit=page_limit, offset=offset)  # type: ignore[arg-type]
