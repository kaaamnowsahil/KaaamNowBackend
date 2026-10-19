"""asyncpg persistence for attendance_records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.attendance.attendance_queries import (
    APPROVE,
    AUTO_APPROVE_CHECKED_OUT,
    INSERT_CHECK_IN,
    SET_CHECK_OUT,
)


async def insert_check_in(
    conn: asyncpg.Connection,
    assignment_id: UUID,
    *,
    now: datetime,
    latitude: float,
    longitude: float,
    distance_m: int,
) -> None:
    await conn.execute(INSERT_CHECK_IN, assignment_id, now, latitude, longitude, distance_m)


async def set_check_out(
    conn: asyncpg.Connection,
    assignment_id: UUID,
    *,
    now: datetime,
    latitude: float | None,
    longitude: float | None,
    note: str,
    recorded_minutes: int,
) -> None:
    await conn.execute(
        SET_CHECK_OUT, assignment_id, now, latitude, longitude, note, recorded_minutes
    )


async def approve(
    conn: asyncpg.Connection,
    assignment_id: UUID,
    *,
    approved_minutes: int,
    note: str,
    now: datetime,
    approver_user_id: UUID,
) -> None:
    await conn.execute(APPROVE, assignment_id, approved_minutes, note, now, approver_user_id)


async def auto_approve_checked_out(
    conn: asyncpg.Connection, shift_id: UUID, *, now: datetime, approver_user_id: UUID
) -> None:
    await conn.execute(AUTO_APPROVE_CHECKED_OUT, shift_id, now, approver_user_id)
