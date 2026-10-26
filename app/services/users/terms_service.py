"""Terms & Conditions acceptance per role, versioned by the page's effective date."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.users.user_route_strings import (
    MSG_TERMS_MISSING,
    MSG_TERMS_REQUIRED,
    TERMS_AUDIENCES,
    USER_AGENT_MAX_LENGTH,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, not_found
from app.repositories.users import terms_repository
from app.schemas.users.user_schemas import TermsStatus
from app.security.authenticated_user import AuthenticatedUser


async def require_accepted(conn: asyncpg.Connection, user_id: UUID, audience: str) -> None:
    """403 ``terms_required`` until the current version is accepted; no page, no check."""
    version = await terms_repository.current_version(conn, audience)
    if version is None:
        return
    if await terms_repository.accepted_at(conn, user_id, audience, version) is None:
        raise ApiError(
            403,
            "terms_required",
            MSG_TERMS_REQUIRED,
            {"audience": audience, "version": version.isoformat()},
        )


async def _status(conn: asyncpg.Connection, user_id: UUID, audience: str) -> TermsStatus:
    version = await terms_repository.current_version(conn, audience)
    accepted_at = (
        await terms_repository.accepted_at(conn, user_id, audience, version) if version else None
    )
    return TermsStatus(
        audience=audience,  # type: ignore[arg-type]
        version=version,
        accepted=version is None or accepted_at is not None,
        accepted_at=accepted_at,
    )


async def list_status(user: AuthenticatedUser) -> list[TermsStatus]:
    async with get_pool().acquire() as conn:
        return [await _status(conn, user.user_id, a) for a in TERMS_AUDIENCES]


async def accept(
    user: AuthenticatedUser, audience: str, ip_address: str | None, user_agent: str | None
) -> TermsStatus:
    async with get_pool().acquire() as conn:
        version = await terms_repository.current_version(conn, audience)
        if version is None:
            raise not_found("terms_not_found", MSG_TERMS_MISSING)
        await terms_repository.insert_acceptance(
            conn,
            user_id=user.user_id,
            audience=audience,
            version=version,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:USER_AGENT_MAX_LENGTH] or None,
        )
        return await _status(conn, user.user_id, audience)
