"""Resolve the caller's Business / Work entities and worker profile (used by every domain service).

An account may own several Business / Work entities. Services scope business-side reads to the
caller's entity ids so one account can never reach another account's shifts, invoices or payments.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.profiles.profile_route_strings import (
    MSG_BUSINESS_NOT_FOUND,
    MSG_BUSINESS_PROFILE_INCOMPLETE,
    MSG_BUSINESS_PROFILE_MISSING,
    MSG_WORKER_NOT_VERIFIED,
    MSG_WORKER_PROFILE_MISSING,
    VERIFICATION_VERIFIED,
)
from app.exceptions.api_errors import bad_request, forbidden, not_found
from app.repositories.profiles import profile_repository
from app.utils.clock import utc_now


async def require_business_profile(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    """The caller's primary Business / Work entity."""
    row = await profile_repository.get_business_profile_by_user(conn, user_id)
    if row is None:
        raise not_found("business_profile_missing", MSG_BUSINESS_PROFILE_MISSING)
    return row


async def require_owned_business(
    conn: asyncpg.Connection, user_id: UUID, business_profile_id: UUID | None
) -> asyncpg.Record:
    """The given entity if the caller owns it, else their primary entity when no id is given."""
    if business_profile_id is None:
        return await require_business_profile(conn, user_id)
    row = await profile_repository.get_business_profile(conn, business_profile_id)
    if row is None or row["user_id"] != user_id:
        raise not_found("business_not_found", MSG_BUSINESS_NOT_FOUND)
    return row


async def business_scope(
    conn: asyncpg.Connection, user_id: UUID, business_profile_id: UUID | None = None
) -> list[UUID]:
    """Entity ids the caller may act on: all of theirs, or the one requested if they own it."""
    ids = await profile_repository.list_business_profile_ids(conn, user_id)
    if not ids:
        raise not_found("business_profile_missing", MSG_BUSINESS_PROFILE_MISSING)
    if business_profile_id is None:
        return ids
    if business_profile_id not in ids:
        raise not_found("business_not_found", MSG_BUSINESS_NOT_FOUND)
    return [business_profile_id]


def ensure_postable(business: asyncpg.Record) -> None:
    """Each shift carries its own site location, so the profile itself only needs a name."""
    if not business["business_name"]:
        raise bad_request("business_profile_incomplete", MSG_BUSINESS_PROFILE_INCOMPLETE)


async def require_postable_business(
    conn: asyncpg.Connection, user_id: UUID, business_profile_id: UUID | None = None
) -> asyncpg.Record:
    row = await require_owned_business(conn, user_id, business_profile_id)
    ensure_postable(row)
    return row


async def require_worker_profile(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    row = await profile_repository.get_worker_profile_by_user(conn, user_id)
    if row is None:
        raise not_found("worker_profile_missing", MSG_WORKER_PROFILE_MISSING)
    return row


async def worker_home_point(
    conn: asyncpg.Connection, worker: asyncpg.Record
) -> tuple[float | None, float | None]:
    """Where shift distance is measured from: recent live location, else the saved address."""
    settings = load_settings()
    location = await profile_repository.get_worker_location(conn, worker["id"])
    valid_since = utc_now() - timedelta(hours=settings.worker_location_valid_hours)
    if location is not None and location["recorded_at"] >= valid_since:
        return location["latitude"], location["longitude"]
    if worker["latitude"] is not None and worker["longitude"] is not None:
        return worker["latitude"], worker["longitude"]
    if location is not None:
        return location["latitude"], location["longitude"]
    return None, None


def ensure_worker_can_work(worker: asyncpg.Record) -> None:
    if load_settings().require_verified_workers and (
        worker["verification_status"] != VERIFICATION_VERIFIED
    ):
        raise forbidden("worker_not_verified", MSG_WORKER_NOT_VERIFIED)
