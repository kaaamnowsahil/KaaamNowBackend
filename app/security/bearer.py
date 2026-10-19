"""Bearer Authorization header parsing."""

from __future__ import annotations

BEARER_PREFIX = "Bearer "


def parse_bearer_token(authorization: str | None) -> str | None:
    """Raw JWT from a Bearer header, or ``None`` if missing / not Bearer / empty."""
    if not authorization or not authorization.startswith(BEARER_PREFIX):
        return None
    token = authorization[len(BEARER_PREFIX) :].strip()
    return token or None
