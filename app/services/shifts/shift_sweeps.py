"""Time-based shift transitions run by the background sweep loop."""

from __future__ import annotations

from datetime import timedelta

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_EXTENSION_PROMPT,
    KIND_LIVE_EXPIRED,
    KIND_SEATS_RELEASED,
    KIND_SELECTION_EXPIRED,
)
from app.constants.shifts.shift_route_strings import (
    APP_EXPIRED,
    SHIFT_AWAITING_PAYMENT,
    SHIFT_EXPIRED,
    SHIFT_FILLED,
    SHIFT_OPEN,
)
from app.repositories.profiles import profile_repository
from app.repositories.shifts import (
    application_repository,
    assignment_repository,
    dispatch_repository,
    shift_repository,
)
from app.services.billing import invoice_service
from app.services.cancellations import cancellation_service
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


async def release_unfilled_seats(pool: asyncpg.Pool) -> int:
    """When applying closes (T−2h) empty seats are released: refunded through the deposit
    and the business gets a free-fees voucher. No bookings at all expires the shift."""
    now = utc_now()
    closes_before = now + timedelta(hours=load_settings().apply_closes_hours_before)
    changed = 0
    async with pool.acquire() as conn:
        for shift_id in await shift_repository.list_open_scheduled_apply_closed(
            conn, closes_before, now
        ):
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                if shift["status"] != SHIFT_OPEN or not now < shift["starts_at"] <= closes_before:
                    continue
                seats = await shift_repository.count_seats(conn, shift_id)
                unfilled = shift["workers_required"] - seats
                if unfilled <= 0:
                    continue
                await shift_repository.set_status(
                    conn,
                    shift_id,
                    from_status=SHIFT_OPEN,
                    to_status=SHIFT_FILLED if seats else SHIFT_EXPIRED,
                    now=now,
                    reason="unfilled_seats_released",
                )
                closed = await application_repository.close_open_applications(
                    conn, shift_id, status=APP_EXPIRED, now=now
                )
                await notify_many(
                    conn,
                    await assignment_repository.user_ids_for_worker_profiles(conn, closed),
                    KIND_SELECTION_EXPIRED,
                    "Shift closed",
                    f"{shift['job_title']} is no longer recruiting.",
                    {"shift_id": shift_id},
                )
                released = await cancellation_service.release_unfilled(conn, shift, unfilled, now)
                if not seats:
                    await invoice_service.settle_cancelled_deposit(conn, shift_id)
                business = await profile_repository.get_business_profile(
                    conn, shift["business_profile_id"]
                )
                await notify(
                    conn,
                    business["user_id"],
                    KIND_SEATS_RELEASED,
                    f"{unfilled} unfilled seat(s) refunded",
                    f"{shift['job_title']}: {seats} of {shift['workers_required']} booked. "
                    "Unfilled seats are refunded in full.",
                    {
                        "shift_id": shift_id,
                        "refund_minor": released.business_refund_minor,
                    },
                )
                changed += 1
    return changed


async def close_scheduled_recruiting(pool: asyncpg.Pool) -> int:
    """At start time an open scheduled shift stops recruiting: filled if anyone booked."""
    now = utc_now()
    changed = 0
    async with pool.acquire() as conn:
        for shift_id in await shift_repository.list_open_scheduled_past_start(conn, now):
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                if shift["starts_at"] > now:
                    continue
                if shift["status"] == SHIFT_AWAITING_PAYMENT:
                    await shift_repository.set_status(
                        conn,
                        shift_id,
                        from_status=SHIFT_AWAITING_PAYMENT,
                        to_status=SHIFT_EXPIRED,
                        now=now,
                        reason="deposit_not_paid",
                    )
                    await invoice_service.settle_cancelled_deposit(conn, shift_id)
                    changed += 1
                    continue
                if shift["status"] != SHIFT_OPEN:
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


async def prompt_extensions(pool: asyncpg.Pool) -> int:
    """Shortly before a worker's end time, ask the business if they need more time."""
    now = utc_now()
    until = now + timedelta(minutes=load_settings().extension_prompt_minutes_before)
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await assignment_repository.list_extension_prompts_due(conn, now, until)
            for row in rows:
                await notify(
                    conn,
                    row["business_user_id"],
                    KIND_EXTENSION_PROMPT,
                    f"{row['full_name'] or 'Your worker'}'s shift ends soon",
                    f"{row['job_title']} — need more time? Request an extension.",
                    {"shift_id": row["shift_id"], "assignment_id": row["id"]},
                )
            if rows:
                await assignment_repository.mark_extension_prompted(
                    conn, [r["id"] for r in rows], now
                )
            return len(rows)
