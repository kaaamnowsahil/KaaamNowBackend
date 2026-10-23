"""The caller's own profile (common /me/profile API), availability and live location.

Business, Worker and plain accounts keep separate data models; the authenticated user's
role decides which one is read, patched, or receives an uploaded image.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import asyncpg
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from app.constants.application.application_constants import ROLE_BUSINESS, ROLE_WORKER
from app.constants.auth.auth_route_strings import MSG_PERMISSION_DENIED
from app.constants.catalog.catalog_route_strings import DIRECTION_BUSINESS_TO_WORKER
from app.constants.profiles.profile_route_strings import (
    MSG_WORKER_LOCATION_REQUIRED,
    MSG_WORKER_NOT_FOUND,
)
from app.constants.users.user_route_strings import (
    AVATAR_STORAGE_FOLDER,
    LOGO_STORAGE_FOLDER,
    MSG_LANGUAGE_UNKNOWN,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import AuthorizationError, bad_request, not_found
from app.repositories.profiles import profile_repository
from app.repositories.ratings import rating_repository
from app.repositories.users import user_repository
from app.schemas.profiles.profile_schemas import (
    AccountProfilePatch,
    AvailabilityRequest,
    AvailabilityResponse,
    BusinessProfilePatch,
    BusinessProfileResponse,
    LocationRequest,
    MyProfileResponse,
    ProfilePatch,
    ProfileType,
    ReviewSnippet,
    WorkerProfilePatch,
    WorkerProfileResponse,
    WorkerPublicProfile,
)
from app.schemas.users.user_schemas import MeResponse
from app.security.authenticated_user import AuthenticatedUser
from app.security.permissions import (
    ACTION_READ,
    ACTION_WRITE,
    RESOURCE_BUSINESS_PROFILE,
    RESOURCE_WORKER_PROFILE,
    roles_allow,
)
from app.services.catalog import catalog_service
from app.services.profiles.profile_lookup import (
    ensure_worker_can_work,
    require_business_profile,
    require_worker_profile,
)
from app.services.users.sources.photo_storage import (
    delete_images,
    get_photo_storage,
    validate_image,
)
from app.services.users.user_service import build_me
from app.utils.address import resolve_locality
from app.utils.clock import utc_now

RECENT_REVIEWS_LIMIT = 5

PROFILE_TYPE_ACCOUNT: Final = "account"
PROFILE_TYPE_BUSINESS: Final = "business"
PROFILE_TYPE_WORKER: Final = "worker"
_ROLE_PROFILE_TYPES: Final[dict[str, ProfileType]] = {
    ROLE_BUSINESS: PROFILE_TYPE_BUSINESS,
    ROLE_WORKER: PROFILE_TYPE_WORKER,
}
_PROFILE_RESOURCES: Final[dict[str, str]] = {
    PROFILE_TYPE_BUSINESS: RESOURCE_BUSINESS_PROFILE,
    PROFILE_TYPE_WORKER: RESOURCE_WORKER_PROFILE,
}
_USER_FIELDS: Final = frozenset({"full_name", "language_code", "theme_preference"})
_PATCH_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    PROFILE_TYPE_ACCOUNT: AccountProfilePatch,
    PROFILE_TYPE_BUSINESS: BusinessProfilePatch,
    PROFILE_TYPE_WORKER: WorkerProfilePatch,
}


def business_profile_response(row: asyncpg.Record) -> BusinessProfileResponse:
    data = dict(row)
    data["rating_avg"] = float(data["rating_avg"])
    return BusinessProfileResponse.model_validate(data)


def worker_profile_response(row: asyncpg.Record) -> WorkerProfileResponse:
    data = dict(row)
    data["rating_avg"] = float(data["rating_avg"])
    data["category_slugs"] = list(data["category_slugs"])
    return WorkerProfileResponse.model_validate(data)


def resolve_profile_type(active_role: str | None, roles: list[str]) -> ProfileType:
    """Pick the profile the caller owns; Business and Worker are mutually exclusive per phone."""
    if active_role in _ROLE_PROFILE_TYPES:
        return _ROLE_PROFILE_TYPES[active_role]
    if active_role is None:
        for role, profile_type in _ROLE_PROFILE_TYPES.items():
            if role in roles:
                return profile_type
    return PROFILE_TYPE_ACCOUNT


async def _resolve_caller(
    conn: asyncpg.Connection, user: AuthenticatedUser, action: str
) -> tuple[MeResponse, ProfileType]:
    me = await build_me(conn, user.user_id)
    profile_type = resolve_profile_type(me.active_role, list(me.roles))
    resource = _PROFILE_RESOURCES.get(profile_type)
    if resource is not None and not roles_allow(user.roles, resource, action):
        raise AuthorizationError(MSG_PERMISSION_DENIED)
    return me, profile_type


async def _profile_response(
    conn: asyncpg.Connection, user_id: UUID, me: MeResponse, profile_type: ProfileType
) -> MyProfileResponse:
    response = MyProfileResponse(profile_type=profile_type, account=me)
    if profile_type == PROFILE_TYPE_BUSINESS:
        response.business = business_profile_response(await require_business_profile(conn, user_id))
    elif profile_type == PROFILE_TYPE_WORKER:
        response.worker = worker_profile_response(await require_worker_profile(conn, user_id))
    return response


def _validate_patch(profile_type: ProfileType, body: ProfilePatch) -> BaseModel:
    schema = _PATCH_SCHEMAS[profile_type]
    try:
        return schema.model_validate(body.model_dump(exclude_unset=True))
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False)
        raise RequestValidationError(
            [{**err, "loc": ("body", *err["loc"])} for err in errors]
        ) from None


async def get_my_profile(user: AuthenticatedUser) -> MyProfileResponse:
    async with get_pool().acquire() as conn:
        me, profile_type = await _resolve_caller(conn, user, ACTION_READ)
        return await _profile_response(conn, user.user_id, me, profile_type)


async def update_my_profile(user: AuthenticatedUser, body: ProfilePatch) -> MyProfileResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _, profile_type = await _resolve_caller(conn, user, ACTION_WRITE)
            patch = _validate_patch(profile_type, body)
            if isinstance(patch, BusinessProfilePatch):
                await _apply_user_fields(conn, user.user_id, patch, owns_email=False)
                await _apply_business_patch(conn, user.user_id, patch)
            elif isinstance(patch, WorkerProfilePatch):
                await _apply_user_fields(conn, user.user_id, patch, owns_email=True)
                await _apply_worker_patch(conn, user.user_id, patch)
            else:
                await _apply_user_fields(conn, user.user_id, patch, owns_email=True)
            me = await build_me(conn, user.user_id)
            return await _profile_response(conn, user.user_id, me, profile_type)


async def upload_my_profile_image(
    user: AuthenticatedUser, content_type: str, data: bytes
) -> MyProfileResponse:
    """Business accounts replace their logo; everyone else replaces their personal photo."""
    extension = validate_image(content_type, data)
    async with get_pool().acquire() as conn:
        _, profile_type = await _resolve_caller(conn, user, ACTION_WRITE)
        if profile_type == PROFILE_TYPE_BUSINESS:
            await require_business_profile(conn, user.user_id)
    is_logo = profile_type == PROFILE_TYPE_BUSINESS
    folder = LOGO_STORAGE_FOLDER if is_logo else AVATAR_STORAGE_FOLDER
    url = await get_photo_storage().save(folder, data, extension)
    try:
        async with get_pool().acquire() as conn:
            if is_logo:
                previous = await profile_repository.replace_business_logo_url(
                    conn, user.user_id, url
                )
            else:
                previous = await user_repository.replace_photo_url(conn, user.user_id, url)
    except BaseException:
        await delete_images([url])
        raise
    await delete_images([previous])
    return await get_my_profile(user)


async def _apply_user_fields(
    conn: asyncpg.Connection,
    user_id: UUID,
    patch: AccountProfilePatch | BusinessProfilePatch | WorkerProfilePatch,
    *,
    owns_email: bool,
) -> None:
    """Write users-table fields; a Business patch's ``email`` belongs to the business row."""
    fields = patch.model_dump(exclude_unset=True)
    email_set = owns_email and "email" in fields
    language = fields.get("language_code")
    if language and not await user_repository.language_is_active(conn, language):
        raise bad_request("language_unknown", MSG_LANGUAGE_UNKNOWN)
    if email_set or fields.keys() & _USER_FIELDS:
        await user_repository.update_user_fields(
            conn,
            user_id,
            full_name=fields.get("full_name"),
            email_set=email_set,
            email=fields.get("email") if email_set else None,
            language_code=language,
            theme_preference=fields.get("theme_preference"),
        )


async def _apply_business_patch(
    conn: asyncpg.Connection, user_id: UUID, body: BusinessProfilePatch
) -> None:
    await require_business_profile(conn, user_id)
    category_id = (
        await catalog_service.resolve_category_id(conn, body.category_slug)
        if body.category_slug
        else None
    )
    business_type_id = (
        await catalog_service.resolve_business_type_id(conn, body.business_type_slug)
        if body.business_type_slug
        else None
    )
    await profile_repository.update_business_profile(
        conn,
        user_id,
        business_name=body.business_name,
        category_id=category_id,
        address_text=body.address_text,
        locality=resolve_locality(body.address_text, body.locality),
        latitude=body.latitude,
        longitude=body.longitude,
        contact_name=body.contact_name,
        email=body.email,
        business_type_id=business_type_id,
    )


async def _apply_worker_patch(
    conn: asyncpg.Connection, user_id: UUID, body: WorkerProfilePatch
) -> None:
    worker = await require_worker_profile(conn, user_id)
    await profile_repository.update_worker_profile(
        conn,
        user_id,
        address_text=body.address_text,
        locality=resolve_locality(body.address_text, body.locality),
        latitude=body.latitude,
        longitude=body.longitude,
        age=body.age,
    )
    if body.category_slugs is not None:
        ids = await catalog_service.resolve_category_ids(conn, body.category_slugs)
        await profile_repository.replace_worker_categories(conn, worker["id"], ids)


async def set_availability(
    user: AuthenticatedUser, body: AvailabilityRequest
) -> AvailabilityResponse:
    """Figma "Go online": online workers must be verified and share a fresh location."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            if body.is_available:
                ensure_worker_can_work(worker)
                if body.latitude is None or body.longitude is None:
                    raise bad_request("location_required", MSG_WORKER_LOCATION_REQUIRED)
                await profile_repository.upsert_worker_location(
                    conn,
                    worker["id"],
                    latitude=body.latitude,
                    longitude=body.longitude,
                    accuracy_m=body.accuracy_m,
                    recorded_at=now,
                )
            else:
                await profile_repository.delete_worker_location(conn, worker["id"])
            await profile_repository.set_worker_availability(
                conn, worker["id"], is_available=body.is_available, now=now
            )
            location = await profile_repository.get_worker_location(conn, worker["id"])
    return AvailabilityResponse(
        is_available=body.is_available,
        availability_changed_at=now,
        location_recorded_at=location["recorded_at"] if location else None,
    )


async def update_location(user: AuthenticatedUser, body: LocationRequest) -> AvailabilityResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        await profile_repository.upsert_worker_location(
            conn,
            worker["id"],
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy_m=body.accuracy_m,
            recorded_at=now,
        )
    return AvailabilityResponse(
        is_available=worker["is_available"],
        availability_changed_at=worker["availability_changed_at"],
        location_recorded_at=now,
    )


async def build_worker_public_profile(
    conn: asyncpg.Connection, worker_profile_id: UUID
) -> WorkerPublicProfile:
    row = await profile_repository.get_worker_profile(conn, worker_profile_id)
    if row is None:
        raise not_found("worker_not_found", MSG_WORKER_NOT_FOUND)
    reviews = await rating_repository.list_recent_reviews(
        conn, row["user_id"], DIRECTION_BUSINESS_TO_WORKER, RECENT_REVIEWS_LIMIT
    )
    return WorkerPublicProfile(
        id=row["id"],
        full_name=row["full_name"],
        photo_url=row["photo_url"],
        locality=row["locality"],
        category_slugs=list(row["category_slugs"]),
        verification_status=row["verification_status"],
        rating_avg=float(row["rating_avg"]),
        rating_count=row["rating_count"],
        completed_shift_count=row["completed_shift_count"],
        member_since=row["created_at"],
        recent_reviews=[
            ReviewSnippet(
                stars=r["stars"],
                tags=list(r["tags"]),
                review=r["review"],
                rater_name=r["rater_name"],
                created_at=r["created_at"],
            )
            for r in reviews
        ],
    )


async def get_worker_public_profile(
    user: AuthenticatedUser, worker_profile_id: UUID
) -> WorkerPublicProfile:
    async with get_pool().acquire() as conn:
        await require_business_profile(conn, user.user_id)
        return await build_worker_public_profile(conn, worker_profile_id)
