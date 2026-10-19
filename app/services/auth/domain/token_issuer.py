"""Issue an access + refresh pair inside the caller's transaction."""

from __future__ import annotations

import uuid
from datetime import timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.repositories.auth import auth_repository
from app.repositories.users import user_repository
from app.schemas.auth.auth_schemas import TokenPair
from app.security.jwt_tokens import hash_refresh_token, issue_access_token, new_refresh_token
from app.utils.clock import utc_now


async def issue_token_pair(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    phone: str,
    family_id: UUID | None = None,
) -> tuple[TokenPair, UUID]:
    """Return ``(tokens, refresh_token_row_id)``. Roles are read fresh from the DB."""
    settings = load_settings()
    roles = await user_repository.list_active_roles(conn, user_id)
    access_token, expires_in = issue_access_token(
        settings, user_id=user_id, phone=phone, roles=roles
    )
    refresh_token = new_refresh_token()
    refresh_id = await auth_repository.insert_refresh_token(
        conn,
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_refresh_token(refresh_token),
        expires_at=utc_now() + timedelta(days=settings.jwt_refresh_days),
    )
    tokens = TokenPair(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )
    return tokens, refresh_id
