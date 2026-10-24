"""asyncpg persistence for shifts, status history, dashboard and discovery."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.repositories.shifts.shift_queries import (
    CANCEL_SHIFT,
    CONVERT_TO_SCHEDULED,
    COUNT_ACTIVE_WORKERS_NEAR,
    COUNT_BUSINESS_SHIFT_GROUPS,
    COUNT_SEATS,
    DASHBOARD_SUMMARY,
    EXPAND_SEARCH_RADIUS,
    FEED_ORDER_BY,
    FEED_TEMPLATE,
    GET_BUSINESS_SHIFT,
    GET_WORKER_SHIFT,
    INSERT_SHIFT,
    INSERT_STATUS_HISTORY,
    LIST_BUSINESS_SHIFTS,
    LIST_DASHBOARD_NEXT_SCHEDULED,
    LIST_DASHBOARD_SHIFTS,
    LIST_DUE_LIVE_EXPANSIONS,
    LIST_LIVE_SEARCHES_TO_REFRESH,
    LIST_OPEN_SCHEDULED_PAST_START,
    LIST_TIMED_OUT_LIVE_SEARCHES,
    LOCK_SHIFT,
    MY_APPLICATION_SHIFTS,
    MY_ASSIGNMENT_SHIFTS,
    PUBLISH_LIVE_SHIFT,
    PUBLISH_SCHEDULED_SHIFT,
    SET_SHIFT_STATUS,
    SET_SHIFT_WINDOW,
    UPDATE_DRAFT_SHIFT,
    WORKER_HAS_OVERLAP,
)

_SHIFT_WRITE_COLUMNS = (
    "category_id",
    "job_title",
    "responsibilities",
    "requirements",
    "workers_required",
    "hourly_rate_minor",
    "starts_at",
    "ends_at",
    "break_minutes",
    "workplace_name",
    "address_text",
    "latitude",
    "longitude",
    "arrival_instructions",
    "site_contact_name",
    "cancellation_cutoff_hours",
)


async def insert_shift(
    conn: asyncpg.Connection,
    *,
    business_profile_id: UUID,
    shift_type: str,
    currency: str,
    check_in_code: str,
    values: dict[str, Any],
) -> UUID:
    return await conn.fetchval(
        INSERT_SHIFT,
        business_profile_id,
        values["category_id"],
        shift_type,
        values["job_title"],
        values["responsibilities"],
        values["requirements"],
        values["workers_required"],
        values["hourly_rate_minor"],
        currency,
        values["starts_at"],
        values["ends_at"],
        values["break_minutes"],
        values["workplace_name"],
        values["address_text"],
        values["latitude"],
        values["longitude"],
        values["arrival_instructions"],
        values["site_contact_name"],
        check_in_code,
        values["cancellation_cutoff_hours"],
    )


async def update_draft_shift(
    conn: asyncpg.Connection, shift_id: UUID, values: dict[str, Any]
) -> None:
    await conn.execute(UPDATE_DRAFT_SHIFT, shift_id, *(values[c] for c in _SHIFT_WRITE_COLUMNS))


async def get_business_shift(
    conn: asyncpg.Connection, shift_id: UUID, business_profile_ids: Sequence[UUID]
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BUSINESS_SHIFT, shift_id, list(business_profile_ids))


async def lock_shift(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_SHIFT, shift_id)


async def set_status(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    from_status: str,
    to_status: str,
    now: datetime,
    actor_user_id: UUID | None = None,
    reason: str = "",
) -> None:
    await conn.execute(SET_SHIFT_STATUS, shift_id, to_status, now)
    await record_history(conn, shift_id, from_status, to_status, actor_user_id, reason)


async def record_history(
    conn: asyncpg.Connection,
    shift_id: UUID,
    from_status: str,
    to_status: str,
    actor_user_id: UUID | None,
    reason: str = "",
) -> None:
    if from_status != to_status:
        await conn.execute(
            INSERT_STATUS_HISTORY, shift_id, from_status, to_status, actor_user_id, reason
        )


async def publish_live(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    now: datetime,
    fee_policy_version: int,
    fee_percentage: Decimal,
    radius_km: float,
    max_radius_km: float,
    expires_at: datetime,
) -> None:
    await conn.execute(
        PUBLISH_LIVE_SHIFT,
        shift_id,
        now,
        fee_policy_version,
        fee_percentage,
        radius_km,
        max_radius_km,
        expires_at,
    )


async def publish_scheduled(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    now: datetime,
    fee_policy_version: int,
    fee_percentage: Decimal,
) -> None:
    await conn.execute(PUBLISH_SCHEDULED_SHIFT, shift_id, now, fee_policy_version, fee_percentage)


async def convert_to_scheduled(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    starts_at: datetime,
    ends_at: datetime,
    now: datetime,
) -> None:
    await conn.execute(CONVERT_TO_SCHEDULED, shift_id, starts_at, ends_at, now)


async def set_window(
    conn: asyncpg.Connection, shift_id: UUID, *, starts_at: datetime, ends_at: datetime
) -> None:
    await conn.execute(SET_SHIFT_WINDOW, shift_id, starts_at, ends_at)


async def cancel_shift(
    conn: asyncpg.Connection, shift_id: UUID, *, now: datetime, reason: str
) -> None:
    await conn.execute(CANCEL_SHIFT, shift_id, now, reason)


async def expand_search_radius(conn: asyncpg.Connection, shift_id: UUID, now: datetime) -> None:
    await conn.execute(EXPAND_SEARCH_RADIUS, shift_id, now)


async def count_seats(conn: asyncpg.Connection, shift_id: UUID) -> int:
    return int(await conn.fetchval(COUNT_SEATS, shift_id))


async def list_business_shifts(
    conn: asyncpg.Connection,
    business_profile_ids: Sequence[UUID],
    *,
    shift_type: str | None,
    statuses: list[str] | None,
    group: str | None,
    now: datetime,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        LIST_BUSINESS_SHIFTS,
        list(business_profile_ids),
        shift_type,
        statuses,
        limit,
        offset,
        now,
        group,
    )


async def count_business_shift_groups(
    conn: asyncpg.Connection,
    business_profile_ids: Sequence[UUID],
    *,
    shift_type: str | None,
    now: datetime,
) -> dict[str, int]:
    rows = await conn.fetch(
        COUNT_BUSINESS_SHIFT_GROUPS, list(business_profile_ids), shift_type, now
    )
    return {row["shift_group"]: row["count"] for row in rows}


async def list_dashboard_shifts(
    conn: asyncpg.Connection, business_profile_ids: Sequence[UUID], shift_type: str, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_DASHBOARD_SHIFTS, list(business_profile_ids), shift_type, now)


async def list_next_scheduled_shifts(
    conn: asyncpg.Connection, business_profile_ids: Sequence[UUID], now: datetime, limit: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_DASHBOARD_NEXT_SCHEDULED, list(business_profile_ids), now, limit)


async def dashboard_summary(
    conn: asyncpg.Connection, business_profile_ids: Sequence[UUID]
) -> asyncpg.Record:
    return await conn.fetchrow(DASHBOARD_SUMMARY, list(business_profile_ids))


async def count_active_workers_near(
    conn: asyncpg.Connection,
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
    require_verified: bool,
    fresh_since: datetime,
    lat_delta: float,
    lng_delta: float,
) -> int:
    return int(
        await conn.fetchval(
            COUNT_ACTIVE_WORKERS_NEAR,
            latitude,
            longitude,
            radius_km,
            require_verified,
            fresh_since,
            lat_delta,
            lng_delta,
        )
    )


async def get_worker_shift(
    conn: asyncpg.Connection,
    shift_id: UUID,
    *,
    worker_profile_id: UUID | None,
    latitude: float | None,
    longitude: float | None,
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WORKER_SHIFT, worker_profile_id, latitude, longitude, shift_id)


async def list_feed(
    conn: asyncpg.Connection,
    *,
    worker_profile_id: UUID,
    own_user_id: UUID,
    latitude: float,
    longitude: float,
    radius_km: float,
    lat_delta: float,
    lng_delta: float,
    shift_type: str | None,
    category_slug: str | None,
    query: str | None,
    sort: str,
    now: datetime,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    sql = FEED_TEMPLATE.format(order_by=FEED_ORDER_BY[sort])
    return await conn.fetch(
        sql,
        worker_profile_id,
        latitude,
        longitude,
        shift_type,
        category_slug,
        query,
        latitude - lat_delta,
        latitude + lat_delta,
        longitude - lng_delta,
        longitude + lng_delta,
        radius_km,
        own_user_id,
        now,
        limit,
        offset,
    )


async def list_my_assignment_shifts(
    conn: asyncpg.Connection,
    worker_profile_id: UUID,
    *,
    statuses: list[str],
    newest_first: bool,
    latitude: float | None,
    longitude: float | None,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        MY_ASSIGNMENT_SHIFTS,
        worker_profile_id,
        latitude,
        longitude,
        statuses,
        limit,
        offset,
        newest_first,
    )


async def list_my_application_shifts(
    conn: asyncpg.Connection,
    worker_profile_id: UUID,
    *,
    statuses: list[str],
    latitude: float | None,
    longitude: float | None,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        MY_APPLICATION_SHIFTS, worker_profile_id, latitude, longitude, statuses, limit, offset
    )


async def worker_has_overlap(
    conn: asyncpg.Connection,
    worker_profile_id: UUID,
    *,
    starts_at: datetime,
    ends_at: datetime,
    exclude_shift_id: UUID,
) -> bool:
    return bool(
        await conn.fetchval(
            WORKER_HAS_OVERLAP, worker_profile_id, starts_at, ends_at, exclude_shift_id
        )
    )


async def list_due_live_expansions(conn: asyncpg.Connection, before: datetime) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(LIST_DUE_LIVE_EXPANSIONS, before)]


async def list_live_searches_to_refresh(conn: asyncpg.Connection, now: datetime) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(LIST_LIVE_SEARCHES_TO_REFRESH, now)]


async def list_timed_out_live_searches(conn: asyncpg.Connection, now: datetime) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(LIST_TIMED_OUT_LIVE_SEARCHES, now)]


async def list_open_scheduled_past_start(conn: asyncpg.Connection, now: datetime) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(LIST_OPEN_SCHEDULED_PAST_START, now)]
