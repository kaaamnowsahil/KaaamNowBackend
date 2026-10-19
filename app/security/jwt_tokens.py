"""HS256 access tokens + opaque refresh tokens.

Access tokens carry ``sub`` (user id), ``phone`` and ``roles``; they are short-lived.
Refresh tokens are random strings; only their SHA-256 is stored (``refresh_tokens``).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

import jwt

from app.config.settings import KaamNowSettings
from app.constants.auth.auth_route_strings import (
    MSG_TOKEN_EXPIRED,
    MSG_TOKEN_INVALID,
    TOKEN_TYPE_ACCESS,
)
from app.exceptions.api_errors import AuthenticationError
from app.security.authenticated_user import AuthenticatedUser
from app.utils.clock import utc_now

_ALGORITHM = "HS256"
_REFRESH_TOKEN_BYTES = 48


def issue_access_token(
    settings: KaamNowSettings, *, user_id: UUID, phone: str, roles: list[str]
) -> tuple[str, int]:
    """Return ``(jwt, expires_in_seconds)``."""
    now = utc_now()
    expires_in = settings.jwt_access_minutes * 60
    claims = {
        "sub": str(user_id),
        "phone": phone,
        "roles": sorted(roles),
        "typ": TOKEN_TYPE_ACCESS,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=_ALGORITHM), expires_in


def verify_access_token(token: str, settings: KaamNowSettings) -> AuthenticatedUser:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(MSG_TOKEN_EXPIRED, code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(MSG_TOKEN_INVALID, code="token_invalid") from exc
    if claims.get("typ") != TOKEN_TYPE_ACCESS:
        raise AuthenticationError(MSG_TOKEN_INVALID, code="token_invalid")
    try:
        user_id = UUID(str(claims["sub"]))
    except ValueError as exc:
        raise AuthenticationError(MSG_TOKEN_INVALID, code="token_invalid") from exc
    roles = claims.get("roles") or []
    return AuthenticatedUser(
        user_id=user_id,
        phone=str(claims.get("phone", "")),
        roles=tuple(str(role) for role in roles),
    )


def new_refresh_token() -> str:
    return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
