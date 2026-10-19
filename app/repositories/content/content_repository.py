"""asyncpg persistence for static content and support tickets."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.repositories.content.content_queries import (
    GET_CONTENT_PAGE,
    INSERT_SUPPORT_TICKET,
    LIST_FAQS,
    USER_CAN_SEE_SHIFT,
)


async def get_content_page(
    conn: asyncpg.Connection, slug: str, audience: str
) -> asyncpg.Record | None:
    """Audience-specific page wins over the ``all`` fallback."""
    return await conn.fetchrow(GET_CONTENT_PAGE, slug, audience)


async def list_faqs(
    conn: asyncpg.Connection, audience: str, search: str | None
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_FAQS, audience, search)


async def user_can_see_shift(conn: asyncpg.Connection, shift_id: UUID, user_id: UUID) -> bool:
    return bool(await conn.fetchval(USER_CAN_SEE_SHIFT, shift_id, user_id))


async def insert_support_ticket(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    topic: str,
    subject: str,
    message: str,
    shift_id: UUID | None,
) -> asyncpg.Record:
    return await conn.fetchrow(INSERT_SUPPORT_TICKET, user_id, topic, subject, message, shift_id)
