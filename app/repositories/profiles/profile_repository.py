"""asyncpg persistence for business / worker profiles and worker live location."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.profiles.profile_queries import (
    DELETE_WORKER_CATEGORIES,
    DELETE_WORKER_LOCATION,
    ENSURE_BUSINESS_PROFILE,
    ENSURE_WORKER_PROFILE,
    GET_BUSINESS_PROFILE_BY_ID,
    GET_BUSINESS_PROFILE_BY_USER,
    GET_WORKER_LOCATION,
    GET_WORKER_PROFILE_BY_ID,
    GET_WORKER_PROFILE_BY_USER,
    INCREMENT_COMPLETED_SHIFTS,
    INSERT_WORKER_CATEGORIES,
    LIST_VERIFICATIONS_BUSINESSES,
    LIST_VERIFICATIONS_WORKERS,
    RECOMPUTE_BUSINESS_RATING,
    RECOMPUTE_WORKER_RATING,
    SET_BUSINESS_VERIFICATION,
    SET_WORKER_AVAILABILITY,
    SET_WORKER_VERIFICATION,
    UPDATE_BUSINESS_PROFILE,
    UPDATE_WORKER_PROFILE,
    UPSERT_WORKER_LOCATION,
)


async def ensure_business_profile(conn: asyncpg.Connection, user_id: UUID) -> None:
    await conn.execute(ENSURE_BUSINESS_PROFILE, user_id)


async def ensure_worker_profile(conn: asyncpg.Connection, user_id: UUID) -> None:
    await conn.execute(ENSURE_WORKER_PROFILE, user_id)


async def get_business_profile_by_user(
    conn: asyncpg.Connection, user_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BUSINESS_PROFILE_BY_USER, user_id)


async def get_business_profile(conn: asyncpg.Connection, profile_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BUSINESS_PROFILE_BY_ID, profile_id)


async def update_business_profile(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    business_name: str | None,
    category_id: UUID | None,
    logo_url: str | None,
    address_text: str | None,
    locality: str | None,
    latitude: float | None,
    longitude: float | None,
) -> None:
    await conn.execute(
        UPDATE_BUSINESS_PROFILE,
        user_id,
        business_name,
        category_id,
        logo_url,
        address_text,
        locality,
        latitude,
        longitude,
    )


async def get_worker_profile_by_user(
    conn: asyncpg.Connection, user_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WORKER_PROFILE_BY_USER, user_id)


async def get_worker_profile(conn: asyncpg.Connection, profile_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WORKER_PROFILE_BY_ID, profile_id)


async def update_worker_profile(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    address_text: str | None,
    locality: str | None,
    latitude: float | None,
    longitude: float | None,
) -> None:
    await conn.execute(UPDATE_WORKER_PROFILE, user_id, address_text, locality, latitude, longitude)


async def replace_worker_categories(
    conn: asyncpg.Connection, worker_profile_id: UUID, category_ids: list[UUID]
) -> None:
    await conn.execute(DELETE_WORKER_CATEGORIES, worker_profile_id)
    if category_ids:
        await conn.execute(INSERT_WORKER_CATEGORIES, worker_profile_id, category_ids)


async def set_worker_availability(
    conn: asyncpg.Connection, worker_profile_id: UUID, *, is_available: bool, now: datetime
) -> None:
    await conn.execute(SET_WORKER_AVAILABILITY, worker_profile_id, is_available, now)


async def upsert_worker_location(
    conn: asyncpg.Connection,
    worker_profile_id: UUID,
    *,
    latitude: float,
    longitude: float,
    accuracy_m: int | None,
    recorded_at: datetime,
) -> None:
    await conn.execute(
        UPSERT_WORKER_LOCATION, worker_profile_id, latitude, longitude, accuracy_m, recorded_at
    )


async def delete_worker_location(conn: asyncpg.Connection, worker_profile_id: UUID) -> None:
    await conn.execute(DELETE_WORKER_LOCATION, worker_profile_id)


async def get_worker_location(
    conn: asyncpg.Connection, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WORKER_LOCATION, worker_profile_id)


async def list_worker_verifications(
    conn: asyncpg.Connection, status: str, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_VERIFICATIONS_WORKERS, status, limit, offset)


async def list_business_verifications(
    conn: asyncpg.Connection, status: str, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_VERIFICATIONS_BUSINESSES, status, limit, offset)


async def set_worker_verification(
    conn: asyncpg.Connection,
    profile_id: UUID,
    *,
    status: str,
    note: str | None,
    now: datetime,
    admin_user_id: UUID,
) -> UUID | None:
    return await conn.fetchval(
        SET_WORKER_VERIFICATION, profile_id, status, note, now, admin_user_id
    )


async def set_business_verification(
    conn: asyncpg.Connection,
    profile_id: UUID,
    *,
    status: str,
    note: str | None,
    now: datetime,
    admin_user_id: UUID,
) -> UUID | None:
    return await conn.fetchval(
        SET_BUSINESS_VERIFICATION, profile_id, status, note, now, admin_user_id
    )


async def recompute_worker_rating(
    conn: asyncpg.Connection, worker_profile_id: UUID, worker_user_id: UUID
) -> None:
    await conn.execute(RECOMPUTE_WORKER_RATING, worker_profile_id, worker_user_id)


async def recompute_business_rating(
    conn: asyncpg.Connection, business_profile_id: UUID, business_user_id: UUID
) -> None:
    await conn.execute(RECOMPUTE_BUSINESS_RATING, business_profile_id, business_user_id)


async def increment_completed_shifts(
    conn: asyncpg.Connection, worker_profile_ids: list[UUID]
) -> None:
    if worker_profile_ids:
        await conn.execute(INCREMENT_COMPLETED_SHIFTS, worker_profile_ids)
