"""asyncpg persistence for users, user_roles and user_devices."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.users.user_queries import (
    DEACTIVATE_DEVICE,
    GET_ME,
    GET_USER_BY_ID,
    LANGUAGE_IS_ACTIVE,
    LIST_ACTIVE_PUSH_TOKENS,
    LIST_ACTIVE_ROLES,
    SET_ACTIVE_ROLE,
    SET_PHOTO_URL,
    TOUCH_LAST_LOGIN,
    UPDATE_USER_FIELDS,
    UPSERT_DEVICE,
    UPSERT_USER_BY_PHONE,
    UPSERT_USER_ROLE,
)


async def upsert_user_by_phone(conn: asyncpg.Connection, phone: str) -> asyncpg.Record:
    """Return the user row plus ``created`` (True on first login)."""
    return await conn.fetchrow(UPSERT_USER_BY_PHONE, phone)


async def touch_last_login(conn: asyncpg.Connection, user_id: UUID, now: datetime) -> None:
    await conn.execute(TOUCH_LAST_LOGIN, user_id, now)


async def get_user(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_USER_BY_ID, user_id)


async def list_active_roles(conn: asyncpg.Connection, user_id: UUID) -> list[str]:
    return [row["role"] for row in await conn.fetch(LIST_ACTIVE_ROLES, user_id)]


async def get_me(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_ME, user_id)


async def update_user_fields(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    full_name: str | None,
    email_set: bool,
    email: str | None,
    language_code: str | None,
    theme_preference: str | None,
) -> None:
    await conn.execute(
        UPDATE_USER_FIELDS, user_id, full_name, email_set, email, language_code, theme_preference
    )


async def set_active_role(conn: asyncpg.Connection, user_id: UUID, role: str) -> None:
    await conn.execute(SET_ACTIVE_ROLE, user_id, role)


async def set_photo_url(conn: asyncpg.Connection, user_id: UUID, photo_url: str) -> None:
    await conn.execute(SET_PHOTO_URL, user_id, photo_url)


async def grant_role(conn: asyncpg.Connection, user_id: UUID, role: str) -> None:
    await conn.execute(UPSERT_USER_ROLE, user_id, role)


async def language_is_active(conn: asyncpg.Connection, code: str) -> bool:
    return bool(await conn.fetchval(LANGUAGE_IS_ACTIVE, code))


async def upsert_device(
    conn: asyncpg.Connection, user_id: UUID, *, platform: str, push_token: str, app_version: str
) -> asyncpg.Record:
    return await conn.fetchrow(UPSERT_DEVICE, user_id, platform, push_token, app_version)


async def deactivate_device(conn: asyncpg.Connection, device_id: UUID, user_id: UUID) -> bool:
    result = await conn.execute(DEACTIVATE_DEVICE, device_id, user_id)
    return result.endswith(" 1")


async def list_active_push_tokens(conn: asyncpg.Connection, user_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_ACTIVE_PUSH_TOKENS, user_id)
