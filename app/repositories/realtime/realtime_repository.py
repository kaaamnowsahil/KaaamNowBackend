"""asyncpg reads for the realtime socket."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.repositories.realtime.realtime_queries import WORKER_PROFILE_ID_BY_USER


async def worker_profile_id(conn: asyncpg.Connection, user_id: UUID) -> UUID | None:
    return await conn.fetchval(WORKER_PROFILE_ID_BY_USER, user_id)
