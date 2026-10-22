"""Work categories + business types: one CRUD group per resource in ``LOOKUP_RESOURCES``."""

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
from app.constants.lookups.lookup_route_strings import (
    DESC_DELETE,
    DESC_GET,
    DESC_LIST,
    LOOKUP_RESOURCES,
    PATH_ITEM_SUFFIX,
    SEARCH_MAX_LENGTH,
    SUMMARY_CREATE,
    SUMMARY_DELETE,
    SUMMARY_GET,
    SUMMARY_LIST,
    SUMMARY_UPDATE,
    LookupResource,
)
from app.dependencies import OptionalUser, RequireVerificationWrite
from app.exceptions.api_errors import AuthenticationError, AuthorizationError
from app.schemas.lookups.lookup_schemas import LookupCreate, LookupItem, LookupUpdate
from app.security.authenticated_user import AuthenticatedUser
from app.security.permissions import ACTION_READ, RESOURCE_VERIFICATION, roles_allow
from app.services.lookups import lookup_service


def _summary(template: str, resource: LookupResource, role: str) -> str:
    return swagger_summary(template.format(label=resource.label), role)


def _can_see_inactive(user: AuthenticatedUser | None) -> bool:
    return user is not None and roles_allow(user.roles, RESOURCE_VERIFICATION, ACTION_READ)


def _require_admin_read(user: AuthenticatedUser | None) -> None:
    if user is None:
        raise AuthenticationError(MSG_AUTHENTICATION_REQUIRED)
    if not _can_see_inactive(user):
        raise AuthorizationError(MSG_PERMISSION_DENIED)


def build_lookup_router(resource: LookupResource) -> APIRouter:
    router = APIRouter(prefix=resource.path, tags=[resource.tag])

    @router.get(
        "",
        response_model=list[LookupItem],
        summary=_summary(SUMMARY_LIST, resource, SWAGGER_ROLE_PUBLIC),
        description=DESC_LIST,
    )
    async def list_items(
        user: OptionalUser,
        include_inactive: bool = Query(default=False),
        q: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    ) -> list[LookupItem]:
        if include_inactive:
            _require_admin_read(user)
        return await lookup_service.list_items(resource, include_inactive=include_inactive, q=q)

    @router.post(
        "",
        response_model=LookupItem,
        status_code=status.HTTP_201_CREATED,
        summary=_summary(SUMMARY_CREATE, resource, SWAGGER_ROLE_ADMIN),
    )
    async def create_item(body: LookupCreate, _: RequireVerificationWrite) -> LookupItem:
        return await lookup_service.create_item(resource, body)

    @router.get(
        PATH_ITEM_SUFFIX,
        response_model=LookupItem,
        summary=_summary(SUMMARY_GET, resource, SWAGGER_ROLE_PUBLIC),
        description=DESC_GET,
    )
    async def get_item(item_id: UUID, user: OptionalUser) -> LookupItem:
        return await lookup_service.get_item(
            resource, item_id, include_inactive=_can_see_inactive(user)
        )

    @router.patch(
        PATH_ITEM_SUFFIX,
        response_model=LookupItem,
        summary=_summary(SUMMARY_UPDATE, resource, SWAGGER_ROLE_ADMIN),
    )
    async def update_item(
        item_id: UUID, body: LookupUpdate, _: RequireVerificationWrite
    ) -> LookupItem:
        return await lookup_service.update_item(resource, item_id, body)

    @router.delete(
        PATH_ITEM_SUFFIX,
        status_code=status.HTTP_204_NO_CONTENT,
        summary=_summary(SUMMARY_DELETE, resource, SWAGGER_ROLE_ADMIN),
        description=DESC_DELETE,
    )
    async def delete_item(item_id: UUID, _: RequireVerificationWrite) -> Response:
        await lookup_service.delete_item(resource, item_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


LOOKUP_ROUTERS: tuple[APIRouter, ...] = tuple(
    build_lookup_router(resource) for resource in LOOKUP_RESOURCES
)
