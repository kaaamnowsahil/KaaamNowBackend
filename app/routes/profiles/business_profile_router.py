"""Business profile (Figma "Business profile")."""

from __future__ import annotations

from fastapi import APIRouter

from app.constants.application.application_common import SWAGGER_ROLE_BUSINESS, swagger_summary
from app.constants.profiles.profile_route_strings import (
    BUSINESS_ROUTE_PREFIX,
    OPENAPI_TAG_BUSINESS_PROFILE,
    PATH_PROFILE,
)
from app.dependencies import RequireBusinessProfileRead, RequireBusinessProfileWrite
from app.schemas.profiles.profile_schemas import BusinessProfilePatch, BusinessProfileResponse
from app.services.profiles import profile_service

router = APIRouter(prefix=BUSINESS_ROUTE_PREFIX, tags=[OPENAPI_TAG_BUSINESS_PROFILE])


@router.get(
    PATH_PROFILE,
    response_model=BusinessProfileResponse,
    summary=swagger_summary("Get business profile", SWAGGER_ROLE_BUSINESS),
)
async def get_profile(user: RequireBusinessProfileRead) -> BusinessProfileResponse:
    return await profile_service.get_business_profile(user)


@router.patch(
    PATH_PROFILE,
    response_model=BusinessProfileResponse,
    summary=swagger_summary("Update business profile", SWAGGER_ROLE_BUSINESS),
)
async def update_profile(
    body: BusinessProfilePatch, user: RequireBusinessProfileWrite
) -> BusinessProfileResponse:
    return await profile_service.update_business_profile(user, body)
