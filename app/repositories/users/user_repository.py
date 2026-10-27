"""asyncpg persistence for users, user_roles and user_devices."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.users.user_queries import (
    DEACTIVATE_DEVICE,
    DEACTIVATE_PUSH_TOKENS,
    DEACTIVATE_USER_ACCOUNT,
    DEACTIVATE_USER_DEVICES,
    GET_AUTH_CREDENTIALS,
    GET_ME,
    GET_PHONE_STATUS,
    GET_PROFILE_IMAGE_URLS,
    GET_USER_BY_ID,
    IS_USER_ACTIVE,
    LANGUAGE_IS_ACTIVE,
    LIST_ACTIVE_PUSH_TOKENS,
    LIST_ACTIVE_ROLES,
    LOCK_USER_BY_ID,
    REPLACE_PHOTO_URL,
    SET_ACTIVE_ROLE,
    SET_PASSWORD_BY_PHONE,
    SET_PASSWORD_IF_MISSING,
    TOUCH_LAST_LOGIN,
    UPDATE_USER_FIELDS,
    UPSERT_DEVICE,
    UPSERT_USER_BY_PHONE,
    UPSERT_USER_ROLE,
)


async def upsert_user_by_phone(conn: asyncpg.Connection, phone: str) -> asyncpg.Record:
    """Return the user row plus ``created`` (True on first login)."""
    return await conn.fetchrow(UPSERT_USER_BY_PHONE, phone)


async def get_phone_status(conn: asyncpg.Connection, phone: str) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_PHONE_STATUS, phone)


async def get_auth_credentials(conn: asyncpg.Connection, phone: str) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_AUTH_CREDENTIALS, phone)


async def set_password_by_phone(conn: asyncpg.Connection, phone: str, password_hash: str) -> bool:
    return await conn.fetchval(SET_PASSWORD_BY_PHONE, phone, password_hash) is not None


async def set_password_if_missing(
    conn: asyncpg.Connection, user_id: UUID, password_hash: str
) -> None:
    await conn.execute(SET_PASSWORD_IF_MISSING, user_id, password_hash)


async def touch_last_login(conn: asyncpg.Connection, user_id: UUID, now: datetime) -> None:
    await conn.execute(TOUCH_LAST_LOGIN, user_id, now)


async def get_user(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_USER_BY_ID, user_id)


async def lock_user(conn: asyncpg.Connection, user_id: UUID) -> None:
    await conn.fetchval(LOCK_USER_BY_ID, user_id)


async def is_user_active(conn: asyncpg.Connection, user_id: UUID) -> bool | None:
    return await conn.fetchval(IS_USER_ACTIVE, user_id)


async def deactivate_account(conn: asyncpg.Connection, user_id: UUID) -> bool:
    return await conn.fetchval(DEACTIVATE_USER_ACCOUNT, user_id) is not None


async def deactivate_devices(conn: asyncpg.Connection, user_id: UUID) -> None:
    await conn.execute(DEACTIVATE_USER_DEVICES, user_id)


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


async def replace_photo_url(conn: asyncpg.Connection, user_id: UUID, photo_url: str) -> str | None:
    """Set the personal photo and return the URL it replaced."""
    return await conn.fetchval(REPLACE_PHOTO_URL, user_id, photo_url)


async def list_profile_image_urls(conn: asyncpg.Connection, user_id: UUID) -> list[str]:
    row = await conn.fetchrow(GET_PROFILE_IMAGE_URLS, user_id)
    if row is None:
        return []
    return [url for url in (row["photo_url"], *row["logo_urls"]) if url]


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


async def deactivate_push_tokens(conn: asyncpg.Connection, push_tokens: list[str]) -> None:
    """Provider said these tokens are dead (app uninstalled, token rotated, other project)."""
    if push_tokens:
        await conn.execute(DEACTIVATE_PUSH_TOKENS, push_tokens)


async def list_active_push_tokens(conn: asyncpg.Connection, user_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_ACTIVE_PUSH_TOKENS, user_id)
