"""Current user: profile + image, Business / Work entities, worker availability / live
location, worker lookup for hirers, deletion, push devices.

Roles are created at ``POST /api/v1/auth/signup``; ``POST /roles`` adds the other one
and ``PUT /active-role`` switches between them.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, Request, UploadFile, status

from app.config.settings import load_settings
from app.constants.application.application_common import (
    SWAGGER_ROLE_ANY_USER,
    SWAGGER_ROLE_BUSINESS,
    SWAGGER_ROLE_WORKER,
    swagger_summary,
)
from app.constants.users.user_route_strings import (
    ME_ROUTE_PREFIX,
    OPENAPI_TAG_ME,
    PATH_ACTIVE_ROLE,
    PATH_AVAILABILITY,
    PATH_BUSINESS,
    PATH_BUSINESS_LOGO,
    PATH_BUSINESSES,
    PATH_CURRENT_DELETION_REQUEST,
    PATH_DELETION_REQUESTS,
    PATH_DEVICE,
    PATH_DEVICES,
    PATH_LOCATION,
    PATH_PROFILE,
    PATH_PROFILE_IMAGE,
    PATH_ROLES,
    PATH_TERMS,
    PATH_TERMS_ACCEPT,
    PATH_WORKER_BY_ID,
)
from app.dependencies import (
    AuthenticatedTokenUser,
    CurrentUser,
    RequireBusinessProfileRead,
    RequireBusinessProfileWrite,
    RequireShiftsRead,
    RequireWorkWrite,
)
from app.schemas.auth.auth_schemas import OtpVerifyResponse, RoleAddRequest
from app.schemas.profiles.profile_schemas import (
    AvailabilityRequest,
    AvailabilityResponse,
    BusinessEntityCreate,
    BusinessEntityPatch,
    BusinessProfileResponse,
    LocationRequest,
    MyProfileResponse,
    ProfilePatch,
    WorkerPublicProfile,
)
from app.schemas.users.deletion_schemas import AccountDeletionRequestResponse
from app.schemas.users.user_schemas import (
    ActiveRoleRequest,
    DeviceRegisterRequest,
    DeviceResponse,
    MeResponse,
    TermsAcceptRequest,
    TermsStatus,
)
from app.services.auth import auth_service
from app.services.profiles import profile_service
from app.services.users import deletion_service, terms_service, user_service

router = APIRouter(prefix=ME_ROUTE_PREFIX, tags=[OPENAPI_TAG_ME])


@router.get(
    PATH_PROFILE,
    response_model=MyProfileResponse,
    summary=swagger_summary(
        "Get my Business / Work, Worker or account profile", SWAGGER_ROLE_ANY_USER
    ),
)
async def get_profile(user: CurrentUser) -> MyProfileResponse:
    return await profile_service.get_my_profile(user)


@router.patch(
    PATH_PROFILE,
    response_model=MyProfileResponse,
    summary=swagger_summary("Update my profile (role-specific fields)", SWAGGER_ROLE_ANY_USER),
)
async def update_profile(body: ProfilePatch, user: CurrentUser) -> MyProfileResponse:
    return await profile_service.update_my_profile(user, body)


@router.post(
    PATH_PROFILE_IMAGE,
    response_model=MyProfileResponse,
    summary=swagger_summary(
        "Upload my profile photo (Business / Work: primary logo) — JPEG, PNG or WebP",
        SWAGGER_ROLE_ANY_USER,
    ),
)
async def upload_profile_image(
    user: CurrentUser, file: UploadFile = File(...)
) -> MyProfileResponse:
    data = await file.read(load_settings().max_photo_bytes + 1)
    return await profile_service.upload_my_profile_image(user, file.content_type or "", data)


@router.get(
    PATH_BUSINESSES,
    response_model=list[BusinessProfileResponse],
    summary=swagger_summary("List my Business / Work profiles", SWAGGER_ROLE_BUSINESS),
)
async def list_businesses(user: RequireBusinessProfileRead) -> list[BusinessProfileResponse]:
    return await profile_service.list_my_businesses(user)


@router.post(
    PATH_BUSINESSES,
    response_model=BusinessProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Add a Business / Work profile", SWAGGER_ROLE_BUSINESS),
)
async def create_business(
    body: BusinessEntityCreate, user: RequireBusinessProfileWrite
) -> BusinessProfileResponse:
    return await profile_service.create_my_business(user, body)


@router.get(
    PATH_BUSINESS,
    response_model=BusinessProfileResponse,
    summary=swagger_summary("Get one of my Business / Work profiles", SWAGGER_ROLE_BUSINESS),
)
async def get_business(
    business_profile_id: UUID, user: RequireBusinessProfileRead
) -> BusinessProfileResponse:
    return await profile_service.get_my_business(user, business_profile_id)


@router.patch(
    PATH_BUSINESS,
    response_model=BusinessProfileResponse,
    summary=swagger_summary("Update one of my Business / Work profiles", SWAGGER_ROLE_BUSINESS),
)
async def update_business(
    business_profile_id: UUID, body: BusinessEntityPatch, user: RequireBusinessProfileWrite
) -> BusinessProfileResponse:
    return await profile_service.update_my_business(user, business_profile_id, body)


@router.post(
    PATH_BUSINESS_LOGO,
    response_model=BusinessProfileResponse,
    summary=swagger_summary(
        "Upload a Business / Work logo — JPEG, PNG or WebP", SWAGGER_ROLE_BUSINESS
    ),
)
async def upload_business_logo(
    business_profile_id: UUID, user: RequireBusinessProfileWrite, file: UploadFile = File(...)
) -> BusinessProfileResponse:
    data = await file.read(load_settings().max_photo_bytes + 1)
    return await profile_service.upload_my_business_logo(
        user, business_profile_id, file.content_type or "", data
    )


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


@router.get(
    PATH_WORKER_BY_ID,
    response_model=WorkerPublicProfile,
    summary=swagger_summary("View a worker's public profile", SWAGGER_ROLE_BUSINESS),
)
async def get_worker(worker_profile_id: UUID, user: RequireShiftsRead) -> WorkerPublicProfile:
    return await profile_service.get_worker_public_profile(user, worker_profile_id)


@router.post(
    PATH_DELETION_REQUESTS,
    response_model=AccountDeletionRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary=swagger_summary("Request account deletion", SWAGGER_ROLE_ANY_USER),
)
async def create_deletion_request(user: CurrentUser) -> AccountDeletionRequestResponse:
    return await deletion_service.create_request(user)


@router.get(
    PATH_CURRENT_DELETION_REQUEST,
    response_model=AccountDeletionRequestResponse,
    summary=swagger_summary("Get account deletion status", SWAGGER_ROLE_ANY_USER),
)
async def get_deletion_request(
    user: AuthenticatedTokenUser,
) -> AccountDeletionRequestResponse:
    return await deletion_service.get_current_request(user.user_id)


@router.post(
    PATH_ROLES,
    response_model=OtpVerifyResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary(
        "Add my other role (Business / Work or Worker); returns new tokens",
        SWAGGER_ROLE_ANY_USER,
    ),
)
async def add_role(body: RoleAddRequest, user: CurrentUser) -> OtpVerifyResponse:
    return await auth_service.add_role(user, body)


@router.put(
    PATH_ACTIVE_ROLE,
    response_model=MeResponse,
    summary=swagger_summary(
        "Switch between my Business / Work and Worker roles", SWAGGER_ROLE_ANY_USER
    ),
)
async def switch_active_role(body: ActiveRoleRequest, user: CurrentUser) -> MeResponse:
    return await user_service.switch_active_role(user, body)


@router.post(
    PATH_DEVICES,
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Register push device", SWAGGER_ROLE_ANY_USER),
)
async def register_device(body: DeviceRegisterRequest, user: CurrentUser) -> DeviceResponse:
    return await user_service.register_device(user, body)


@router.delete(
    PATH_DEVICE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Unregister push device", SWAGGER_ROLE_ANY_USER),
)
async def unregister_device(device_id: UUID, user: CurrentUser) -> None:
    await user_service.unregister_device(user, device_id)


@router.get(
    PATH_TERMS,
    response_model=list[TermsStatus],
    summary=swagger_summary("Terms & Conditions acceptance status", SWAGGER_ROLE_ANY_USER),
)
async def get_terms_status(user: CurrentUser) -> list[TermsStatus]:
    return await terms_service.list_status(user)


@router.post(
    PATH_TERMS_ACCEPT,
    response_model=TermsStatus,
    summary=swagger_summary("Accept the current Terms & Conditions", SWAGGER_ROLE_ANY_USER),
)
async def accept_terms(
    body: TermsAcceptRequest, request: Request, user: CurrentUser
) -> TermsStatus:
    return await terms_service.accept(
        user,
        body.audience,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
