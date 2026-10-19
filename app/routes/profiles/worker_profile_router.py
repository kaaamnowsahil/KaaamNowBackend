"""Worker profile, go-online toggle, live location; business view of a worker."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.constants.application.application_common import (
    SWAGGER_ROLE_BUSINESS,
    SWAGGER_ROLE_WORKER,
    swagger_summary,
)
from app.constants.profiles.profile_route_strings import (
    OPENAPI_TAG_WORKER_PROFILE,
    PATH_AVAILABILITY,
    PATH_LOCATION,
    PATH_PROFILE,
    PATH_WORKER_BY_ID,
    WORKER_ROUTE_PREFIX,
    WORKERS_ROUTE_PREFIX,
)
from app.dependencies import RequireShiftsRead, RequireWorkWrite, RequireWorkerProfileWrite
from app.schemas.profiles.profile_schemas import (
    AvailabilityRequest,
    AvailabilityResponse,
    LocationRequest,
    WorkerProfilePatch,
    WorkerProfileResponse,
    WorkerPublicProfile,
)
from app.services.profiles import profile_service

router = APIRouter(prefix=WORKER_ROUTE_PREFIX, tags=[OPENAPI_TAG_WORKER_PROFILE])
workers_router = APIRouter(prefix=WORKERS_ROUTE_PREFIX, tags=[OPENAPI_TAG_WORKER_PROFILE])


@router.get(
    PATH_PROFILE,
    response_model=WorkerProfileResponse,
    summary=swagger_summary("Get worker profile", SWAGGER_ROLE_WORKER),
)
async def get_profile(user: RequireWorkerProfileWrite) -> WorkerProfileResponse:
    return await profile_service.get_worker_profile(user)


@router.patch(
    PATH_PROFILE,
    response_model=WorkerProfileResponse,
    summary=swagger_summary("Update worker profile", SWAGGER_ROLE_WORKER),
)
async def update_profile(
    body: WorkerProfilePatch, user: RequireWorkerProfileWrite
) -> WorkerProfileResponse:
    return await profile_service.update_worker_profile(user, body)


@router.put(
    PATH_AVAILABILITY,
    response_model=AvailabilityResponse,
    summary=swagger_summary("Go online / offline", SWAGGER_ROLE_WORKER),
)
async def set_availability(
    body: AvailabilityRequest, user: RequireWorkWrite
) -> AvailabilityResponse:
    return await profile_service.set_availability(user, body)


@router.put(
    PATH_LOCATION,
    response_model=AvailabilityResponse,
    summary=swagger_summary("Update live location", SWAGGER_ROLE_WORKER),
)
async def update_location(body: LocationRequest, user: RequireWorkWrite) -> AvailabilityResponse:
    return await profile_service.update_location(user, body)


@workers_router.get(
    PATH_WORKER_BY_ID,
    response_model=WorkerPublicProfile,
    summary=swagger_summary("View worker profile", SWAGGER_ROLE_BUSINESS),
)
async def get_worker(worker_profile_id: UUID, user: RequireShiftsRead) -> WorkerPublicProfile:
    return await profile_service.get_worker_public_profile(user, worker_profile_id)
