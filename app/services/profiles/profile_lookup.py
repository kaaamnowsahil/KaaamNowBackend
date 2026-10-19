"""Resolve the caller's business / worker profile (used by every domain service)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.profiles.profile_route_strings import (
    MSG_BUSINESS_PROFILE_INCOMPLETE,
    MSG_BUSINESS_PROFILE_MISSING,
    MSG_WORKER_NOT_VERIFIED,
    MSG_WORKER_PROFILE_MISSING,
    VERIFICATION_VERIFIED,
)
from app.exceptions.api_errors import bad_request, forbidden, not_found
from app.repositories.profiles import profile_repository


async def require_business_profile(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    row = await profile_repository.get_business_profile_by_user(conn, user_id)
    if row is None:
        raise not_found("business_profile_missing", MSG_BUSINESS_PROFILE_MISSING)
    return row


async def require_postable_business(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    row = await require_business_profile(conn, user_id)
    if not row["business_name"] or row["latitude"] is None:
        raise bad_request("business_profile_incomplete", MSG_BUSINESS_PROFILE_INCOMPLETE)
    return row


async def require_worker_profile(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record:
    row = await profile_repository.get_worker_profile_by_user(conn, user_id)
    if row is None:
        raise not_found("worker_profile_missing", MSG_WORKER_PROFILE_MISSING)
    return row


def ensure_worker_can_work(worker: asyncpg.Record) -> None:
    if load_settings().require_verified_workers and (
        worker["verification_status"] != VERIFICATION_VERIFIED
    ):
        raise forbidden("worker_not_verified", MSG_WORKER_NOT_VERIFIED)
