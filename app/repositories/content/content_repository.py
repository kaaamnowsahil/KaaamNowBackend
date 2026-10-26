"""asyncpg persistence for static content and support tickets."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.repositories.content.content_queries import (
    ADMIN_DELETE_FAQ,
    ADMIN_DELETE_TERMS,
    ADMIN_GET_FAQ,
    ADMIN_INSERT_FAQ,
    ADMIN_LIST_FAQS,
    ADMIN_LIST_TERMS,
    ADMIN_UPDATE_FAQ,
    ADMIN_UPSERT_TERMS,
    GET_CONTENT_PAGE,
    INSERT_SUPPORT_TICKET,
    LIST_ACTIVE_ADMIN_USER_IDS,
    LIST_FAQS,
    USER_CAN_SEE_SHIFT,
)


async def admin_list_faqs(
    conn: asyncpg.Connection, audience: str | None, include_inactive: bool
) -> list[asyncpg.Record]:
    return await conn.fetch(ADMIN_LIST_FAQS, audience, include_inactive)


async def admin_get_faq(conn: asyncpg.Connection, faq_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(ADMIN_GET_FAQ, faq_id)


async def admin_insert_faq(conn: asyncpg.Connection, values: dict) -> asyncpg.Record:
    return await conn.fetchrow(
        ADMIN_INSERT_FAQ,
        values["audience"],
        values["slug"],
        values["question"],
        values["answer"],
        values["sort_order"],
        values["is_active"],
    )


async def admin_update_faq(
    conn: asyncpg.Connection, faq_id: UUID, values: dict
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        ADMIN_UPDATE_FAQ,
        faq_id,
        values["audience"],
        values["slug"],
        values["question"],
        values["answer"],
        values["sort_order"],
        values["is_active"],
    )


async def admin_delete_faq(conn: asyncpg.Connection, faq_id: UUID) -> bool:
    return await conn.execute(ADMIN_DELETE_FAQ, faq_id) != "DELETE 0"


async def admin_list_pages(conn: asyncpg.Connection, slug: str) -> list[asyncpg.Record]:
    return await conn.fetch(ADMIN_LIST_TERMS, slug)


async def admin_upsert_page(
    conn: asyncpg.Connection, slug: str, audience: str, values: dict
) -> asyncpg.Record:
    return await conn.fetchrow(
        ADMIN_UPSERT_TERMS,
        slug,
        audience,
        values["title"],
        values["body_markdown"],
        values["effective_date"],
    )


async def admin_delete_page(conn: asyncpg.Connection, slug: str, audience: str) -> bool:
    return await conn.execute(ADMIN_DELETE_TERMS, slug, audience) != "DELETE 0"


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
    priority: str = "normal",
    assignment_id: UUID | None = None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        INSERT_SUPPORT_TICKET, user_id, topic, subject, message, shift_id, priority, assignment_id
    )


async def list_active_admin_user_ids(conn: asyncpg.Connection) -> list[UUID]:
    return [r["user_id"] for r in await conn.fetch(LIST_ACTIVE_ADMIN_USER_IDS)]
