"""Read worker shift filter options and manage them as an admin."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.constants.application.application_common import (
    SWAGGER_ROLE_ADMIN,
    SWAGGER_ROLE_PUBLIC,
    swagger_summary,
)
from app.constants.auth.auth_route_strings import (
    MSG_AUTHENTICATION_REQUIRED,
    MSG_PERMISSION_DENIED,
)
from app.dependencies import OptionalUser, RequireVerificationWrite
from app.exceptions.api_errors import AuthenticationError, AuthorizationError
from app.schemas.lookups.shift_filter_schemas import (
    ShiftFilterOption,
    ShiftFilterOptionCreate,
    ShiftFilterOptionUpdate,
)
from app.security.authenticated_user import AuthenticatedUser
from app.security.permissions import ACTION_READ, RESOURCE_VERIFICATION, roles_allow
from app.services.lookups import shift_filter_service

router = APIRouter(prefix="/api/v1/shift-filter-options", tags=["shift filter options"])


def _can_read_inactive(user: AuthenticatedUser | None) -> bool:
    return user is not None and roles_allow(user.roles, RESOURCE_VERIFICATION, ACTION_READ)


def _require_admin_read(user: AuthenticatedUser | None) -> None:
    if user is None:
        raise AuthenticationError(MSG_AUTHENTICATION_REQUIRED)
    if not _can_read_inactive(user):
        raise AuthorizationError(MSG_PERMISSION_DENIED)


@router.get(
    "",
    response_model=list[ShiftFilterOption],
    summary=swagger_summary("List worker shift filter options", SWAGGER_ROLE_PUBLIC),
)
async def list_options(
    user: OptionalUser,
    include_inactive: bool = Query(default=False),
) -> list[ShiftFilterOption]:
    if include_inactive:
        _require_admin_read(user)
    return await shift_filter_service.list_options(include_inactive=include_inactive)


@router.post(
    "",
    response_model=ShiftFilterOption,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Create worker shift filter option", SWAGGER_ROLE_ADMIN),
)
async def create_option(
    body: ShiftFilterOptionCreate, _: RequireVerificationWrite
) -> ShiftFilterOption:
    return await shift_filter_service.create_option(body)


@router.get(
    "/{option_id}",
    response_model=ShiftFilterOption,
    summary=swagger_summary("Get worker shift filter option", SWAGGER_ROLE_PUBLIC),
)
async def get_option(option_id: UUID, user: OptionalUser) -> ShiftFilterOption:
    return await shift_filter_service.get_option(
        option_id, include_inactive=_can_read_inactive(user)
    )


@router.patch(
    "/{option_id}",
    response_model=ShiftFilterOption,
    summary=swagger_summary("Update worker shift filter option", SWAGGER_ROLE_ADMIN),
)
async def update_option(
    option_id: UUID,
    body: ShiftFilterOptionUpdate,
    _: RequireVerificationWrite,
) -> ShiftFilterOption:
    return await shift_filter_service.update_option(option_id, body)


@router.delete(
    "/{option_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Deactivate worker shift filter option", SWAGGER_ROLE_ADMIN),
)
async def delete_option(option_id: UUID, _: RequireVerificationWrite) -> Response:
    await shift_filter_service.delete_option(option_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
