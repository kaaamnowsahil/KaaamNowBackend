"""Authenticated principal extracted from a verified access token."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Request-scoped identity attached after JWT verification."""

    user_id: UUID
    phone: str
    roles: tuple[str, ...]

    def has_role(self, role: str) -> bool:
        return role in self.roles
