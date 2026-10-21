"""Verify Firebase phone-auth ID tokens against Google's published signing keys.

The client signs in with Firebase (which sends and checks the SMS OTP) and posts the
resulting ID token here; we only trust the verified ``phone_number`` claim from it.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx
import jwt

from app.config.settings import load_settings
from app.constants.auth.auth_route_strings import (
    FIREBASE_ISSUER_PREFIX,
    FIREBASE_JWKS_DEFAULT_TTL_SECONDS,
    FIREBASE_JWKS_TIMEOUT_SECONDS,
    FIREBASE_JWKS_URL,
    FIREBASE_SIGNING_ALGORITHM,
    MSG_FIREBASE_NOT_CONFIGURED,
    MSG_FIREBASE_PHONE_MISSING,
    MSG_FIREBASE_TOKEN_INVALID,
    MSG_FIREBASE_UNAVAILABLE,
)
from app.exceptions.api_errors import ApiError, AuthenticationError
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)

_MAX_AGE = re.compile(r"max-age=(\d+)")
_jwks: dict[str, jwt.PyJWK] = {}
_jwks_expires_at = 0.0
_jwks_lock = asyncio.Lock()


def _service_unavailable() -> ApiError:
    return ApiError(503, "firebase_unavailable", MSG_FIREBASE_UNAVAILABLE)


async def _signing_keys(force_refresh: bool = False) -> dict[str, jwt.PyJWK]:
    global _jwks, _jwks_expires_at
    async with _jwks_lock:
        if _jwks and not force_refresh and time.monotonic() < _jwks_expires_at:
            return _jwks
        try:
            async with httpx.AsyncClient(timeout=FIREBASE_JWKS_TIMEOUT_SECONDS) as client:
                response = await client.get(FIREBASE_JWKS_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("firebase jwks fetch failed", extra=log_extra(error=str(exc)))
            if _jwks:
                return _jwks
            raise _service_unavailable() from exc
        match = _MAX_AGE.search(response.headers.get("cache-control", ""))
        ttl = int(match.group(1)) if match else FIREBASE_JWKS_DEFAULT_TTL_SECONDS
        _jwks = {
            key["kid"]: jwt.PyJWK(key, algorithm=FIREBASE_SIGNING_ALGORITHM)
            for key in response.json().get("keys", [])
            if key.get("kid")
        }
        _jwks_expires_at = time.monotonic() + ttl
        return _jwks


async def verify_firebase_phone_token(id_token: str) -> str:
    """Return the verified E.164 phone number from a Firebase ID token."""
    project_id = load_settings().firebase_project_id.strip()
    if not project_id:
        raise ApiError(503, "firebase_not_configured", MSG_FIREBASE_NOT_CONFIGURED)
    invalid = AuthenticationError(MSG_FIREBASE_TOKEN_INVALID, code="firebase_token_invalid")
    try:
        kid = jwt.get_unverified_header(id_token).get("kid")
    except jwt.PyJWTError as exc:
        raise invalid from exc
    keys = await _signing_keys()
    if kid not in keys:
        keys = await _signing_keys(force_refresh=True)
    signing_key = keys.get(kid)
    if signing_key is None:
        raise invalid
    try:
        claims: dict[str, Any] = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=[FIREBASE_SIGNING_ALGORITHM],
            audience=project_id,
            issuer=f"{FIREBASE_ISSUER_PREFIX}{project_id}",
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise invalid from exc
    if not claims.get("sub") or claims.get("auth_time", 0) > time.time() + 60:
        raise invalid
    phone = claims.get("phone_number")
    if not phone:
        raise AuthenticationError(MSG_FIREBASE_PHONE_MISSING, code="firebase_phone_missing")
    return str(phone)
