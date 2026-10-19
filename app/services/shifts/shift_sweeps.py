"""Time-based shift transitions run by the background sweep loop."""

from __future__ import annotations

from datetime import timedelta

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_LIVE_EXPIRED,
    KIND_SELECTION_EXPIRED,
)
from app.constants.shifts.shift_route_strings import (
    APP_EXPIRED,
    SHIFT_EXPIRED,
    SHIFT_FILLED,
    SHIFT_OPEN,
)
from app.repositories.profiles import profile_repository
from app.repositories.shifts import application_repository, dispatch_repository, shift_repository
from app.services.notifications.notification_service import notify, notify_many
from app.services.shifts import live_dispatch_service
from app.utils.clock import utc_now


async def expire_live_offers(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await dispatch_repository.expire_due_offers(conn, utc_now())


async def refresh_live_searches(pool: asyncpg.Pool) -> int:
    """Expand radius when due, then offer to workers who came online since the last round."""
    settings = load_settings()
    now = utc_now()
    sent = 0
    async with pool.acquire() as conn:
        due = await shift_repository.list_due_live_expansions(
            conn, now - timedelta(seconds=settings.live_radius_expand_after_seconds)
        )
        for shift_id in due:
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                if shift["radius_expanded_at"] is None:
                    await shift_repository.expand_search_radius(conn, shift_id, now)
        for shift_id in await shift_repository.list_live_searches_to_refresh(conn, now):
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                sent += await live_dispatch_service.dispatch_round(conn, shift, now)
    return sent


async def finish_live_searches(pool: asyncpg.Pool) -> int:
    now = utc_now()
    changed = 0
    async with pool.acquire() as conn:
        for shift_id in await shift_repository.list_timed_out_live_searches(conn, now):
            async with conn.transaction():
                changed += int(await live_dispatch_service.finish_search(conn, shift_id, now))
    return changed


async def expire_selection_confirmations(pool: asyncpg.Pool) -> int:
    now = utc_now()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await application_repository.expire_due_selections(conn, now)
            for row in rows:
                worker = await profile_repository.get_worker_profile(conn, row["worker_profile_id"])
                business = await profile_repository.get_business_profile(
                    conn, row["business_profile_id"]
                )
                await notify(
                    conn,
                    worker["user_id"],
                    KIND_SELECTION_EXPIRED,
                    "Selection expired",
                    f"You didn't confirm {row['job_title']} in time.",
                    {"shift_id": row["shift_id"], "application_id": row["id"]},
                )
                await notify(
                    conn,
                    business["user_id"],
                    KIND_SELECTION_EXPIRED,
                    "A selected worker didn't confirm",
                    f"Pick another applicant for {row['job_title']}.",
                    {"shift_id": row["shift_id"], "application_id": row["id"]},
                )
    return len(rows)


async def close_scheduled_recruiting(pool: asyncpg.Pool) -> int:
    """At start time an open scheduled shift stops recruiting: filled if anyone booked."""
    now = utc_now()
    changed = 0
    async with pool.acquire() as conn:
        for shift_id in await shift_repository.list_open_scheduled_past_start(conn, now):
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                if shift["status"] != SHIFT_OPEN or shift["starts_at"] > now:
                    continue
                seats = await shift_repository.count_seats(conn, shift_id)
                target = SHIFT_FILLED if seats else SHIFT_EXPIRED
                await shift_repository.set_status(
                    conn,
                    shift_id,
                    from_status=SHIFT_OPEN,
                    to_status=target,
                    now=now,
                    reason="start_time_reached",
                )
                closed = await application_repository.close_open_applications(
                    conn, shift_id, status=APP_EXPIRED, now=now
                )
                await notify_many(
                    conn,
                    [
                        (await profile_repository.get_worker_profile(conn, wid))["user_id"]
                        for wid in closed
                    ],
                    KIND_SELECTION_EXPIRED,
                    "Shift closed",
                    f"{shift['job_title']} is no longer recruiting.",
                    {"shift_id": shift_id},
                )
                if not seats:
                    business = await profile_repository.get_business_profile(
                        conn, shift["business_profile_id"]
                    )
                    await notify(
                        conn,
                        business["user_id"],
                        KIND_LIVE_EXPIRED,
                        "No workers booked",
                        f"{shift['job_title']} started without any confirmed workers.",
                        {"shift_id": shift_id},
                    )
                changed += 1
    return changed
