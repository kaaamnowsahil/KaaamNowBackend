"""Business / worker profile reads and edits, availability and live location."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.catalog.catalog_route_strings import DIRECTION_BUSINESS_TO_WORKER
from app.constants.profiles.profile_route_strings import (
    LOGO_STORAGE_FOLDER,
    MSG_WORKER_LOCATION_REQUIRED,
    MSG_WORKER_NOT_FOUND,
)
from app.constants.users.user_route_strings import (
    ALLOWED_PHOTO_CONTENT_TYPES,
    MSG_PHOTO_TOO_LARGE,
    MSG_PHOTO_TYPE,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, not_found
from app.repositories.profiles import profile_repository
from app.repositories.ratings import rating_repository
from app.repositories.users import user_repository
from app.schemas.profiles.profile_schemas import (
    AvailabilityRequest,
    AvailabilityResponse,
    BusinessProfilePatch,
    BusinessProfileResponse,
    LocationRequest,
    ReviewSnippet,
    WorkerProfilePatch,
    WorkerProfileResponse,
    WorkerPublicProfile,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.catalog import catalog_service
from app.services.profiles.profile_lookup import (
    ensure_worker_can_work,
    require_business_profile,
    require_worker_profile,
)
from app.services.users.sources.photo_storage import get_photo_storage
from app.utils.address import resolve_locality
from app.utils.clock import utc_now

RECENT_REVIEWS_LIMIT = 5


def business_profile_response(row: asyncpg.Record) -> BusinessProfileResponse:
    data = dict(row)
    data["rating_avg"] = float(data["rating_avg"])
    return BusinessProfileResponse.model_validate(data)


def worker_profile_response(row: asyncpg.Record) -> WorkerProfileResponse:
    data = dict(row)
    data["rating_avg"] = float(data["rating_avg"])
    data["category_slugs"] = list(data["category_slugs"])
    return WorkerProfileResponse.model_validate(data)


async def get_business_profile(user: AuthenticatedUser) -> BusinessProfileResponse:
    async with get_pool().acquire() as conn:
        return business_profile_response(await require_business_profile(conn, user.user_id))


async def update_business_profile(
    user: AuthenticatedUser, body: BusinessProfilePatch
) -> BusinessProfileResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await require_business_profile(conn, user.user_id)
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
                user.user_id,
                business_name=body.business_name,
                category_id=category_id,
                logo_url=body.logo_url,
                address_text=body.address_text,
                locality=resolve_locality(body.address_text, body.locality),
                latitude=body.latitude,
                longitude=body.longitude,
                contact_name=body.contact_name,
                email=body.email,
                business_type_id=business_type_id,
            )
            return business_profile_response(await require_business_profile(conn, user.user_id))


async def upload_business_logo(
    user: AuthenticatedUser, content_type: str, data: bytes
) -> BusinessProfileResponse:
    extension = ALLOWED_PHOTO_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise bad_request("photo_type", MSG_PHOTO_TYPE)
    if len(data) > load_settings().max_photo_bytes:
        raise bad_request("photo_too_large", MSG_PHOTO_TOO_LARGE)
    async with get_pool().acquire() as conn:
        await require_business_profile(conn, user.user_id)
    url = await get_photo_storage().save(LOGO_STORAGE_FOLDER, data, extension)
    async with get_pool().acquire() as conn:
        await profile_repository.update_business_profile(
            conn,
            user.user_id,
            business_name=None,
            category_id=None,
            logo_url=url,
            address_text=None,
            locality=None,
            latitude=None,
            longitude=None,
        )
        return business_profile_response(await require_business_profile(conn, user.user_id))


async def get_worker_profile(user: AuthenticatedUser) -> WorkerProfileResponse:
    async with get_pool().acquire() as conn:
        return worker_profile_response(await require_worker_profile(conn, user.user_id))


async def update_worker_profile(
    user: AuthenticatedUser, body: WorkerProfilePatch
) -> WorkerProfileResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            patch = body.model_dump(exclude_unset=True)
            if "full_name" in patch or "email" in patch:
                await user_repository.update_user_fields(
                    conn,
                    user.user_id,
                    full_name=body.full_name,
                    email_set="email" in patch,
                    email=body.email,
                    language_code=None,
                    theme_preference=None,
                )
            await profile_repository.update_worker_profile(
                conn,
                user.user_id,
                address_text=body.address_text,
                locality=resolve_locality(body.address_text, body.locality),
                latitude=body.latitude,
                longitude=body.longitude,
                age=body.age,
            )
            if body.category_slugs is not None:
                ids = await catalog_service.resolve_category_ids(conn, body.category_slugs)
                await profile_repository.replace_worker_categories(conn, worker["id"], ids)
            return worker_profile_response(await require_worker_profile(conn, user.user_id))


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
