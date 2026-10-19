"""Current user: profile, preferences, roles, devices, photo."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_BUSINESS, ROLE_WORKER
from app.constants.users.user_route_strings import (
    ALLOWED_PHOTO_CONTENT_TYPES,
    MSG_DEVICE_NOT_FOUND,
    MSG_LANGUAGE_UNKNOWN,
    MSG_PHOTO_TOO_LARGE,
    MSG_PHOTO_TYPE,
    MSG_ROLE_NOT_HELD,
    MSG_USER_NOT_FOUND,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, forbidden, not_found
from app.repositories.profiles import profile_repository
from app.repositories.users import user_repository
from app.schemas.auth.auth_schemas import OtpVerifyResponse
from app.schemas.users.user_schemas import (
    BusinessProfileSummary,
    DeviceRegisterRequest,
    DeviceResponse,
    MePatch,
    MeResponse,
    WorkerProfileSummary,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.auth.domain.token_issuer import issue_token_pair
from app.services.users.sources.photo_storage import get_photo_storage

_PROFILE_ENSURERS = {
    ROLE_BUSINESS: profile_repository.ensure_business_profile,
    ROLE_WORKER: profile_repository.ensure_worker_profile,
}


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


async def get_me(user: AuthenticatedUser) -> MeResponse:
    async with get_pool().acquire() as conn:
        return await build_me(conn, user.user_id)


async def update_me(user: AuthenticatedUser, body: MePatch) -> MeResponse:
    patch = body.model_dump(exclude_unset=True)
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            language = patch.get("language_code")
            if language and not await user_repository.language_is_active(conn, language):
                raise bad_request("language_unknown", MSG_LANGUAGE_UNKNOWN)
            await user_repository.update_user_fields(
                conn,
                user.user_id,
                full_name=patch.get("full_name"),
                email_set="email" in patch,
                email=patch.get("email"),
                language_code=language,
                theme_preference=patch.get("theme_preference"),
            )
            return await build_me(conn, user.user_id)


async def set_active_role(user: AuthenticatedUser, role: str) -> MeResponse:
    async with get_pool().acquire() as conn:
        roles = await user_repository.list_active_roles(conn, user.user_id)
        if role not in roles:
            raise forbidden("role_not_held", MSG_ROLE_NOT_HELD)
        await user_repository.set_active_role(conn, user.user_id, role)
        return await build_me(conn, user.user_id)


async def add_role(user: AuthenticatedUser, role: str) -> OtpVerifyResponse:
    """Figma "How will you use KaamNow?": grant role, create its profile, switch to it.

    Returns fresh tokens because the access token embeds the role list.
    """
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await user_repository.grant_role(conn, user.user_id, role)
            await _PROFILE_ENSURERS[role](conn, user.user_id)
            await user_repository.set_active_role(conn, user.user_id, role)
            tokens, _ = await issue_token_pair(conn, user_id=user.user_id, phone=user.phone)
            me = await build_me(conn, user.user_id)
    return OtpVerifyResponse(tokens=tokens, is_new_user=False, needs_role_selection=False, me=me)


async def upload_photo(user: AuthenticatedUser, content_type: str, data: bytes) -> MeResponse:
    settings = load_settings()
    extension = ALLOWED_PHOTO_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise bad_request("photo_type", MSG_PHOTO_TYPE)
    if len(data) > settings.max_photo_bytes:
        raise bad_request("photo_too_large", MSG_PHOTO_TOO_LARGE)
    url = await get_photo_storage().save("avatars", data, extension)
    async with get_pool().acquire() as conn:
        await user_repository.set_photo_url(conn, user.user_id, url)
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
