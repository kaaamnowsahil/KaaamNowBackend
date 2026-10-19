"""asyncpg persistence for otp_challenges and refresh_tokens."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.auth.auth_queries import (
    CONSUME_OPEN_OTP_CHALLENGES,
    COUNT_OTP_SENDS_SINCE,
    INSERT_OTP_CHALLENGE,
    INSERT_REFRESH_TOKEN,
    LOCK_LATEST_OPEN_OTP_CHALLENGE,
    LOCK_REFRESH_TOKEN_BY_HASH,
    MARK_REFRESH_TOKEN_ROTATED,
    RECORD_OTP_ATTEMPT,
    REVOKE_REFRESH_TOKEN_BY_HASH,
    REVOKE_REFRESH_TOKEN_FAMILY,
)


async def count_otp_sends_since(
    conn: asyncpg.Connection, phone: str, since: datetime
) -> asyncpg.Record:
    return await conn.fetchrow(COUNT_OTP_SENDS_SINCE, phone, since)


async def replace_otp_challenge(
    conn: asyncpg.Connection,
    *,
    phone: str,
    code_hash: str,
    expires_at: datetime,
    request_ip: str | None,
    now: datetime,
) -> asyncpg.Record:
    await conn.execute(CONSUME_OPEN_OTP_CHALLENGES, phone, now)
    return await conn.fetchrow(INSERT_OTP_CHALLENGE, phone, code_hash, expires_at, request_ip)


async def lock_latest_open_otp_challenge(
    conn: asyncpg.Connection, phone: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_LATEST_OPEN_OTP_CHALLENGE, phone)


async def record_otp_attempt(
    conn: asyncpg.Connection, challenge_id: UUID, *, matched: bool, now: datetime
) -> None:
    await conn.execute(RECORD_OTP_ATTEMPT, challenge_id, matched, now)


async def insert_refresh_token(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    family_id: UUID,
    token_hash: str,
    expires_at: datetime,
) -> UUID:
    return await conn.fetchval(INSERT_REFRESH_TOKEN, user_id, family_id, token_hash, expires_at)


async def lock_refresh_token(conn: asyncpg.Connection, token_hash: str) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_REFRESH_TOKEN_BY_HASH, token_hash)


async def mark_refresh_token_rotated(
    conn: asyncpg.Connection, token_id: UUID, *, replaced_by_id: UUID, now: datetime
) -> None:
    await conn.execute(MARK_REFRESH_TOKEN_ROTATED, token_id, now, replaced_by_id)


async def revoke_refresh_token_family(
    conn: asyncpg.Connection, family_id: UUID, now: datetime
) -> None:
    await conn.execute(REVOKE_REFRESH_TOKEN_FAMILY, family_id, now)


async def revoke_refresh_token(
    conn: asyncpg.Connection, token_hash: str, *, user_id: UUID, now: datetime
) -> None:
    await conn.execute(REVOKE_REFRESH_TOKEN_BY_HASH, token_hash, now, user_id)
