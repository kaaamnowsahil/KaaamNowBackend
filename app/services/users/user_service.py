"""Current user account summary and push devices (profiles live in profile_service)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.users.user_route_strings import (
    MSG_DEVICE_NOT_FOUND,
    MSG_ROLE_NOT_REGISTERED,
    MSG_USER_NOT_FOUND,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import (
    not_found,
)
from app.repositories.users import user_repository
from app.schemas.users.user_schemas import (
    ActiveRoleRequest,
    BusinessProfileSummary,
    DeviceRegisterRequest,
    DeviceResponse,
    MeResponse,
    WorkerProfileSummary,
)
from app.security.authenticated_user import AuthenticatedUser


async def build_me(conn: asyncpg.Connection, user_id: UUID) -> MeResponse:
    row = await user_repository.get_me(conn, user_id)
    if row is None:
        raise not_found("user_not_found", MSG_USER_NOT_FOUND)
    business = (
        BusinessProfileSummary(
            id=row["business_profile_id"],
            business_name=row["business_name"],
            verification_status=row["business_verification"],
        )
        if row["business_profile_id"]
        else None
    )
    worker = (
        WorkerProfileSummary(
            id=row["worker_profile_id"],
            verification_status=row["worker_verification"],
            is_available=row["is_available"],
        )
        if row["worker_profile_id"]
        else None
    )
    return MeResponse(
        id=row["id"],
        phone=row["phone"],
        full_name=row["full_name"],
        email=row["email"],
        photo_url=row["photo_url"],
        language_code=row["language_code"],
        theme_preference=row["theme_preference"],
        active_role=row["active_role"],
        roles=list(row["roles"]),
        business_profile=business,
        worker_profile=worker,
        created_at=row["created_at"],
    )


async def switch_active_role(user: AuthenticatedUser, body: ActiveRoleRequest) -> MeResponse:
    async with get_pool().acquire() as conn:
        if body.role not in await user_repository.list_active_roles(conn, user.user_id):
            raise not_found("role_not_registered", MSG_ROLE_NOT_REGISTERED.format(role=body.role))
        await user_repository.set_active_role(conn, user.user_id, body.role)
        return await build_me(conn, user.user_id)


async def register_device(user: AuthenticatedUser, body: DeviceRegisterRequest) -> DeviceResponse:
    async with get_pool().acquire() as conn:
        row = await user_repository.upsert_device(
            conn,
            user.user_id,
            platform=body.platform,
            push_token=body.push_token,
            app_version=body.app_version,
        )
    return DeviceResponse.model_validate(dict(row))


async def unregister_device(user: AuthenticatedUser, device_id: UUID) -> None:
    async with get_pool().acquire() as conn:
        if not await user_repository.deactivate_device(conn, device_id, user.user_id):
            raise not_found("device_not_found", MSG_DEVICE_NOT_FOUND)
