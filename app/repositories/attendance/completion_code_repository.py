"""asyncpg persistence for assignment_completion_codes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

INSERT_CODE = """
INSERT INTO assignment_completion_codes (assignment_id, shift_id, code)
VALUES ($1, $2, $3)
ON CONFLICT (assignment_id) DO NOTHING
"""
GET_CODE = "SELECT * FROM assignment_completion_codes WHERE assignment_id = $1"
LOCK_CODE = "SELECT * FROM assignment_completion_codes WHERE assignment_id = $1 FOR UPDATE"
RECORD_FAILED_ATTEMPT = """
UPDATE assignment_completion_codes SET failed_attempts = failed_attempts + 1,
    locked_at = CASE WHEN failed_attempts + 1 >= $2 THEN $3 ELSE locked_at END,
    updated_at = now()
WHERE assignment_id = $1 AND verified_at IS NULL
RETURNING failed_attempts, locked_at
"""
SET_VERIFIED = """
UPDATE assignment_completion_codes SET verified_at = $2, updated_at = now()
WHERE assignment_id = $1 AND verified_at IS NULL
"""
REISSUE_CODE = """
UPDATE assignment_completion_codes SET code = $2, failed_attempts = 0, locked_at = NULL,
    issued_count = issued_count + 1, updated_at = now()
WHERE assignment_id = $1 AND verified_at IS NULL
"""


async def insert_code(
    conn: asyncpg.Connection, *, assignment_id: UUID, shift_id: UUID, code: str
) -> None:
    await conn.execute(INSERT_CODE, assignment_id, shift_id, code)


async def get_code(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_CODE, assignment_id)


async def lock_code(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_CODE, assignment_id)


async def record_failed_attempt(
    conn: asyncpg.Connection, assignment_id: UUID, *, max_attempts: int, now: datetime
) -> asyncpg.Record | None:
    return await conn.fetchrow(RECORD_FAILED_ATTEMPT, assignment_id, max_attempts, now)


async def set_verified(conn: asyncpg.Connection, assignment_id: UUID, now: datetime) -> None:
    await conn.execute(SET_VERIFIED, assignment_id, now)


async def reissue_code(conn: asyncpg.Connection, assignment_id: UUID, *, code: str) -> None:
    await conn.execute(REISSUE_CODE, assignment_id, code)
