"""Self-issued JWT (after phone OTP) and the central RBAC matrix."""

from app.security.authenticated_user import AuthenticatedUser
from app.security.permissions import role_allows

__all__ = ["AuthenticatedUser", "role_allows"]
