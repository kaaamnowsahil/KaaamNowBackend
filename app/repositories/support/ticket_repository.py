"""SQL for admin support-ticket status changes."""

from __future__ import annotations

from uuid import UUID

import asyncpg

_COLUMNS = """
id, user_id, topic, subject, message, shift_id, assignment_id, status, priority,
resolution_note, resolved_by_user_id, resolved_at, created_at, updated_at
"""

LOCK_TICKET = f"SELECT {_COLUMNS} FROM support_tickets WHERE id = $1 FOR UPDATE"

START_TICKET = f"""
UPDATE support_tickets
SET status = 'in_progress', updated_at = now()
WHERE id = $1
RETURNING {_COLUMNS}
"""

CLOSE_TICKET = f"""
UPDATE support_tickets
SET status = 'closed',
    resolved_at = now(),
    resolved_by_user_id = $2,
    resolution_note = COALESCE($3, resolution_note),
    updated_at = now()
WHERE id = $1
RETURNING {_COLUMNS}
"""


async def lock(conn: asyncpg.Connection, ticket_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_TICKET, ticket_id)


async def start(conn: asyncpg.Connection, ticket_id: UUID) -> asyncpg.Record:
    row = await conn.fetchrow(START_TICKET, ticket_id)
    assert row is not None
    return row


async def close(
    conn: asyncpg.Connection, ticket_id: UUID, admin_user_id: UUID, note: str | None
) -> asyncpg.Record:
    row = await conn.fetchrow(CLOSE_TICKET, ticket_id, admin_user_id, note)
    assert row is not None
    return row
