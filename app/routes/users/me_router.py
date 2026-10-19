"""Current user: profile, language, appearance, role selection, photo, push devices."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, UploadFile, status

from app.constants.application.application_common import SWAGGER_ROLE_ANY_USER, swagger_summary
from app.constants.users.user_route_strings import (
    ME_ROUTE_PREFIX,
    OPENAPI_TAG_ME,
    PATH_ACTIVE_ROLE,
    PATH_DEVICE,
    PATH_DEVICES,
    PATH_PHOTO,
    PATH_ROLES,
)
from app.dependencies import CurrentUser
from app.schemas.auth.auth_schemas import OtpVerifyResponse
from app.schemas.users.user_schemas import (
    ActiveRoleRequest,
    AddRoleRequest,
    DeviceRegisterRequest,
    DeviceResponse,
    MePatch,
    MeResponse,
)
from app.services.users import user_service

router = APIRouter(prefix=ME_ROUTE_PREFIX, tags=[OPENAPI_TAG_ME])


@router.get("", response_model=MeResponse, summary=swagger_summary("Get me", SWAGGER_ROLE_ANY_USER))
async def get_me(user: CurrentUser) -> MeResponse:
    return await user_service.get_me(user)


@router.patch(
    "", response_model=MeResponse, summary=swagger_summary("Update me", SWAGGER_ROLE_ANY_USER)
)
async def update_me(body: MePatch, user: CurrentUser) -> MeResponse:
    return await user_service.update_me(user, body)


@router.put(
    PATH_ACTIVE_ROLE,
    response_model=MeResponse,
    summary=swagger_summary("Switch active role", SWAGGER_ROLE_ANY_USER),
)
async def set_active_role(body: ActiveRoleRequest, user: CurrentUser) -> MeResponse:
    return await user_service.set_active_role(user, body.role)


@router.post(
    PATH_ROLES,
    response_model=OtpVerifyResponse,
    summary=swagger_summary(
        "Add Business or Worker role (returns new tokens)", SWAGGER_ROLE_ANY_USER
    ),
)
async def add_role(body: AddRoleRequest, user: CurrentUser) -> OtpVerifyResponse:
    return await user_service.add_role(user, body.role)


@router.post(
    PATH_PHOTO,
    response_model=MeResponse,
    summary=swagger_summary("Upload profile photo", SWAGGER_ROLE_ANY_USER),
)
async def upload_photo(user: CurrentUser, file: UploadFile = File(...)) -> MeResponse:
    data = await file.read()
    return await user_service.upload_photo(user, file.content_type or "", data)


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
