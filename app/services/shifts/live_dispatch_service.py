"""Live shifts: offer to nearby online workers, first-come accept, fill / expire.

Figma: "Finding workers nearby", worker "New request nearby · Accept within 04:59".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_LIVE_ACCEPTED,
    KIND_LIVE_EXPIRED,
    KIND_LIVE_FILLED,
    KIND_LIVE_REQUEST,
)
from app.constants.shifts.shift_route_strings import (
    DISPATCH_ACCEPTED,
    DISPATCH_DECLINED,
    DISPATCH_EXPIRED,
    DISPATCH_OFFERED,
    MSG_ALREADY_BOOKED,
    MSG_LOCATION_STALE,
    MSG_NO_LIVE_OFFER,
    MSG_NOT_LIVE_SHIFT,
    MSG_OVERLAPPING_SHIFT,
    MSG_SHIFT_FULL,
    MSG_SHIFT_NOT_FOUND,
    MSG_SHIFT_NOT_RECRUITING,
    MSG_TOO_FAR_FROM_SHIFT,
    SHIFT_EXPIRED,
    SHIFT_FILLED,
    SHIFT_LIVE,
    SHIFT_SEARCHING,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.repositories.profiles import profile_repository
from app.repositories.shifts import assignment_repository, dispatch_repository, shift_repository
from app.schemas.shifts.assignment_schemas import AssignmentDetail
from app.schemas.shifts.shift_schemas import LiveRequestItem
from app.security.authenticated_user import AuthenticatedUser
from app.services.live_work import live_work_hooks
from app.services.notifications.notification_service import notify, notify_many
from app.services.profiles.profile_lookup import ensure_worker_can_work, require_worker_profile
from app.services.shifts.domain.shift_mappers import worker_shift_card
from app.utils.clock import utc_now
from app.utils.geo import bounding_box_deltas, haversine_km


async def _business_user_id(conn: asyncpg.Connection, business_profile_id: UUID) -> UUID:
    row = await profile_repository.get_business_profile(conn, business_profile_id)
    return row["user_id"]


async def dispatch_round(conn: asyncpg.Connection, shift: asyncpg.Record, now: datetime) -> int:
    """Offer the shift to eligible workers inside the current radius. Returns offers sent."""
    settings = load_settings()
    if shift["status"] != SHIFT_SEARCHING or shift["search_expires_at"] <= now:
        return 0
    seats = await shift_repository.count_seats(conn, shift["id"])
    if seats >= shift["workers_required"]:
        return 0
    radius = shift["search_radius_km"]
    lat_delta, lng_delta = bounding_box_deltas(shift["latitude"], radius)
    business_user_id = await _business_user_id(conn, shift["business_profile_id"])
    candidates = await dispatch_repository.list_candidates(
        conn,
        shift=shift,
        radius_km=radius,
        require_verified=settings.require_verified_workers,
        fresh_since=now - timedelta(seconds=settings.location_freshness_seconds),
        lat_delta=lat_delta,
        lng_delta=lng_delta,
        business_user_id=business_user_id,
        limit=settings.live_dispatch_batch_size,
    )
    if not candidates:
        return 0
    expires_at = min(
        now + timedelta(seconds=settings.live_offer_timeout_seconds), shift["search_expires_at"]
    )
    offered = await dispatch_repository.insert_offers(
        conn,
        shift_id=shift["id"],
        radius_km=radius,
        expires_at=expires_at,
        worker_profile_ids=[c["worker_profile_id"] for c in candidates],
        distances_km=[float(c["distance_km"]) for c in candidates],
    )
    offered_set = set(offered)
    user_ids = [c["user_id"] for c in candidates if c["worker_profile_id"] in offered_set]
    await notify_many(
        conn,
        user_ids,
        KIND_LIVE_REQUEST,
        f"New request nearby: {shift['job_title']}",
        "Accept quickly — first come, first served.",
        {"shift_id": shift["id"], "expires_at": expires_at.isoformat()},
    )
    return len(offered)


async def mark_filled(
    conn: asyncpg.Connection, shift: asyncpg.Record, now: datetime, reason: str = ""
) -> None:
    await shift_repository.set_status(
        conn,
        shift["id"],
        from_status=shift["status"],
        to_status=SHIFT_FILLED,
        now=now,
        reason=reason,
    )
    await dispatch_repository.withdraw_open_offers(conn, shift["id"])


async def finish_search(conn: asyncpg.Connection, shift_id: UUID, now: datetime) -> bool:
    """Search timed out: keep whoever accepted (filled) or expire. Returns True if changed."""
    shift = await shift_repository.lock_shift(conn, shift_id)
    if shift is None or shift["status"] != SHIFT_SEARCHING or shift["search_expires_at"] > now:
        return False
    seats = await shift_repository.count_seats(conn, shift_id)
    business_user_id = await _business_user_id(conn, shift["business_profile_id"])
    if seats > 0:
        await mark_filled(conn, shift, now, reason="search_timeout_partial")
        await notify(
            conn,
            business_user_id,
            KIND_LIVE_FILLED,
            f"{seats} of {shift['workers_required']} workers booked",
            f"The live search for {shift['job_title']} has ended.",
            {"shift_id": shift_id},
        )
    else:
        await shift_repository.set_status(
            conn,
            shift_id,
            from_status=SHIFT_SEARCHING,
            to_status=SHIFT_EXPIRED,
            now=now,
            reason="search_timeout",
        )
        await dispatch_repository.withdraw_open_offers(conn, shift_id)
        if not await live_work_hooks.on_search_expired(conn, shift, business_user_id):
            await notify(
                conn,
                business_user_id,
                KIND_LIVE_EXPIRED,
                "No workers available right now",
                "Try again or post it as a scheduled shift.",
                {"shift_id": shift_id},
            )
    return True


async def list_live_requests(user: AuthenticatedUser) -> list[LiveRequestItem]:
    now = utc_now()
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        location = await profile_repository.get_worker_location(conn, worker["id"])
        lat = location["latitude"] if location else None
        lng = location["longitude"] if location else None
        items: list[LiveRequestItem] = []
        for offer in await dispatch_repository.list_open_offers_for_worker(conn, worker["id"], now):
            row = await shift_repository.get_worker_shift(
                conn, offer["shift_id"], worker_profile_id=worker["id"], latitude=lat, longitude=lng
            )
            if row is None:
                continue
            items.append(
                LiveRequestItem(
                    dispatch_id=offer["dispatch_id"],
                    expires_at=offer["expires_at"],
                    seconds_left=max(int((offer["expires_at"] - now).total_seconds()), 0),
                    shift=worker_shift_card(row),
                )
            )
    return items


async def _eligible_distance(
    conn: asyncpg.Connection, worker: asyncpg.Record, shift: asyncpg.Record, now: datetime
) -> float:
    settings = load_settings()
    location = await profile_repository.get_worker_location(conn, worker["id"])
    fresh_since = now - timedelta(seconds=settings.location_freshness_seconds)
    if location is None or location["recorded_at"] < fresh_since or not worker["is_available"]:
        raise bad_request("location_stale", MSG_LOCATION_STALE)
    distance = haversine_km(
        location["latitude"], location["longitude"], shift["latitude"], shift["longitude"]
    )
    if distance > shift["search_radius_km"]:
        raise bad_request("too_far", MSG_TOO_FAR_FROM_SHIFT)
    return distance


async def accept(user: AuthenticatedUser, shift_id: UUID) -> AssignmentDetail:
    from app.services.shifts.assignment_service import build_assignment_detail

    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            ensure_worker_can_work(worker)
            shift = await shift_repository.lock_shift(conn, shift_id)
            if shift is None:
                raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
            if shift["shift_type"] != SHIFT_LIVE:
                raise bad_request("not_live_shift", MSG_NOT_LIVE_SHIFT)
            if shift["status"] != SHIFT_SEARCHING or shift["search_expires_at"] <= now:
                raise conflict("shift_not_recruiting", MSG_SHIFT_NOT_RECRUITING)
            seats = await shift_repository.count_seats(conn, shift_id)
            if seats >= shift["workers_required"]:
                raise conflict("shift_full", MSG_SHIFT_FULL)

            dispatch = await dispatch_repository.lock_dispatch(conn, shift_id, worker["id"])
            if dispatch is not None and dispatch["status"] == DISPATCH_ACCEPTED:
                raise conflict("already_booked", MSG_ALREADY_BOOKED)
            if dispatch is not None and dispatch["status"] == DISPATCH_DECLINED:
                raise conflict("no_live_offer", MSG_NO_LIVE_OFFER)
            offer_live = (
                dispatch is not None
                and dispatch["status"] == DISPATCH_OFFERED
                and dispatch["expires_at"] > now
            )
            if offer_live:
                await dispatch_repository.set_status(conn, dispatch["id"], DISPATCH_ACCEPTED, now)
                dispatch_id = dispatch["id"]
            else:
                if dispatch is not None and dispatch["status"] not in (
                    DISPATCH_OFFERED,
                    DISPATCH_EXPIRED,
                ):
                    raise conflict("no_live_offer", MSG_NO_LIVE_OFFER)
                distance = await _eligible_distance(conn, worker, shift, now)
                dispatch_id = await dispatch_repository.upsert_accepted(
                    conn,
                    shift_id=shift_id,
                    worker_profile_id=worker["id"],
                    radius_km=shift["search_radius_km"],
                    distance_km=distance,
                    now=now,
                )
                if dispatch_id is None:
                    raise conflict("no_live_offer", MSG_NO_LIVE_OFFER)

            if await shift_repository.worker_has_overlap(
                conn,
                worker["id"],
                starts_at=shift["starts_at"],
                ends_at=shift["ends_at"],
                exclude_shift_id=shift_id,
            ):
                raise conflict("overlapping_shift", MSG_OVERLAPPING_SHIFT)
            try:
                async with conn.transaction():
                    assignment_id = await assignment_repository.insert_assignment(
                        conn,
                        shift_id=shift_id,
                        worker_profile_id=worker["id"],
                        source=SHIFT_LIVE,
                        dispatch_id=dispatch_id,
                        application_id=None,
                        hourly_rate_minor=shift["hourly_rate_minor"],
                        now=now,
                    )
            except asyncpg.UniqueViolationError:
                raise conflict("already_booked", MSG_ALREADY_BOOKED) from None
            await live_work_hooks.on_accepted(conn, shift, assignment_id, now)

            business_user_id = await _business_user_id(conn, shift["business_profile_id"])
            worker_name = worker["full_name"] or "A worker"
            await notify(
                conn,
                business_user_id,
                KIND_LIVE_ACCEPTED,
                f"{worker_name} accepted your shift",
                f"{shift['job_title']} · {seats + 1} of {shift['workers_required']} booked",
                {"shift_id": shift_id, "assignment_id": assignment_id},
            )
            if seats + 1 >= shift["workers_required"]:
                await mark_filled(conn, shift, now, reason="all_seats_accepted")
                await notify(
                    conn,
                    business_user_id,
                    KIND_LIVE_FILLED,
                    "All workers found",
                    f"Your live shift {shift['job_title']} is fully booked.",
                    {"shift_id": shift_id},
                )
            return await build_assignment_detail(conn, assignment_id, user)


async def decline(user: AuthenticatedUser, shift_id: UUID) -> None:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            dispatch = await dispatch_repository.lock_dispatch(conn, shift_id, worker["id"])
            if dispatch is None or dispatch["status"] != DISPATCH_OFFERED:
                raise conflict("no_live_offer", MSG_NO_LIVE_OFFER)
            await dispatch_repository.set_status(conn, dispatch["id"], DISPATCH_DECLINED, now)
