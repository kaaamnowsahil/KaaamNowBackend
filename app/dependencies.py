"""FastAPI dependencies for authentication and centralized authorization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import load_settings
from app.constants.auth.auth_route_strings import (
    DESC_SWAGGER_BEARER,
    MSG_ACCOUNT_DISABLED,
    MSG_AUTHENTICATION_REQUIRED,
    MSG_PERMISSION_DENIED,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import AuthenticationError, AuthorizationError
from app.repositories.users import user_repository
from app.security.authenticated_user import AuthenticatedUser
from app.security.bearer import parse_bearer_token
from app.security.jwt_tokens import verify_access_token
from app.security.permissions import (
    ACTION_READ,
    ACTION_WRITE,
    RESOURCE_BILLING,
    RESOURCE_BUSINESS_PROFILE,
    RESOURCE_EARNINGS,
    RESOURCE_SHIFTS,
    RESOURCE_VERIFICATION,
    RESOURCE_WORK,
    roles_allow,
)

# Declares Bearer in OpenAPI so Swagger UI shows "Authorize".
_swagger_bearer = HTTPBearer(auto_error=False, bearerFormat="JWT", description=DESC_SWAGGER_BEARER)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_swagger_bearer)] = None,
) -> AuthenticatedUser:
    """Verify the access token once per request and attach the user to ``request.state``."""
    existing = getattr(request.state, "user", None)
    if isinstance(existing, AuthenticatedUser):
        return existing
    token = credentials.credentials if credentials else None
    token = token or parse_bearer_token(request.headers.get("authorization"))
    if not token:
        raise AuthenticationError(MSG_AUTHENTICATION_REQUIRED)
    user = verify_access_token(token, load_settings())
    async with get_pool().acquire() as conn:
        is_active = await user_repository.is_user_active(conn, user.user_id)
    if not is_active:
        raise AuthenticationError(MSG_ACCOUNT_DISABLED, code="account_disabled")
    request.state.user = user
    return user


async def get_authenticated_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_swagger_bearer)] = None,
) -> AuthenticatedUser:
    """Verify a signed access token without checking account activity.

    This is reserved for an account's deletion-status endpoint after completion,
    when the account has been disabled and its refresh tokens revoked.
    """
    existing = getattr(request.state, "user", None)
    if isinstance(existing, AuthenticatedUser):
        return existing
    token = credentials.credentials if credentials else None
    token = token or parse_bearer_token(request.headers.get("authorization"))
    if not token:
        raise AuthenticationError(MSG_AUTHENTICATION_REQUIRED)
    return verify_access_token(token, load_settings())


def require_access(resource: str, action: str) -> Callable[..., AuthenticatedUser]:
    """Dependency factory: authenticate + authorize via the central matrix.

    Routers must not embed role checks — use the aliases below.
    """

    async def _dependency(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if not roles_allow(user.roles, resource, action):
            raise AuthorizationError(MSG_PERMISSION_DENIED)
        return user

    return _dependency


async def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_swagger_bearer)] = None,
) -> AuthenticatedUser | None:
    """Like ``get_current_user`` but public routes get ``None`` instead of a 401."""
    try:
        return await get_current_user(request, credentials)
    except AuthenticationError:
        return None


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
AuthenticatedTokenUser = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_user)]

RequireBusinessProfileRead = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_BUSINESS_PROFILE, ACTION_READ))
]
RequireBusinessProfileWrite = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_BUSINESS_PROFILE, ACTION_WRITE))
]
RequireShiftsRead = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_SHIFTS, ACTION_READ))
]
RequireShiftsWrite = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_SHIFTS, ACTION_WRITE))
]
RequireBillingRead = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_BILLING, ACTION_READ))
]
RequireBillingWrite = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_BILLING, ACTION_WRITE))
]
RequireWorkRead = Annotated[AuthenticatedUser, Depends(require_access(RESOURCE_WORK, ACTION_READ))]
RequireWorkWrite = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_WORK, ACTION_WRITE))
]
RequireEarningsRead = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_EARNINGS, ACTION_READ))
]
RequireEarningsWrite = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_EARNINGS, ACTION_WRITE))
]
RequireVerificationRead = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_VERIFICATION, ACTION_READ))
]
RequireVerificationWrite = Annotated[
    AuthenticatedUser, Depends(require_access(RESOURCE_VERIFICATION, ACTION_WRITE))
]
