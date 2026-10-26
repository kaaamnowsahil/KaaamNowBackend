"""asyncpg persistence for Terms & Conditions acceptance."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

import asyncpg

CURRENT_TERMS_VERSION = """
SELECT effective_date FROM content_pages
WHERE slug = 'terms' AND audience IN ($1, 'all')
ORDER BY (audience = $1) DESC
LIMIT 1
"""

GET_ACCEPTANCE = """
SELECT accepted_at FROM terms_acceptances WHERE user_id = $1 AND audience = $2 AND version = $3
"""

INSERT_ACCEPTANCE = """
INSERT INTO terms_acceptances (user_id, audience, version, ip_address, user_agent)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (user_id, audience, version) DO NOTHING
"""


async def current_version(conn: asyncpg.Connection, audience: str) -> date | None:
    return await conn.fetchval(CURRENT_TERMS_VERSION, audience)


async def accepted_at(
    conn: asyncpg.Connection, user_id: UUID, audience: str, version: date
) -> datetime | None:
    return await conn.fetchval(GET_ACCEPTANCE, user_id, audience, version)


async def insert_acceptance(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    audience: str,
    version: date,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    await conn.execute(INSERT_ACCEPTANCE, user_id, audience, version, ip_address, user_agent)
