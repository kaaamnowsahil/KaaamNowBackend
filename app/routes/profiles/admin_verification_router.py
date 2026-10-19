"""Admin: verify workers and businesses."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.constants.profiles.profile_route_strings import (
    ADMIN_ROUTE_PREFIX,
    OPENAPI_TAG_ADMIN,
    PATH_ADMIN_BUSINESS_VERIFICATION,
    PATH_ADMIN_VERIFICATIONS,
    PATH_ADMIN_WORKER_VERIFICATION,
)
from app.dependencies import RequireVerificationRead, RequireVerificationWrite
from app.schemas.profiles.profile_schemas import (
    BusinessProfileResponse,
    VerificationDecision,
    VerificationQueue,
    WorkerProfileResponse,
)
from app.services.profiles import verification_service

router = APIRouter(prefix=ADMIN_ROUTE_PREFIX, tags=[OPENAPI_TAG_ADMIN])


@router.get(
    PATH_ADMIN_VERIFICATIONS,
    response_model=VerificationQueue,
    summary=swagger_summary("Verification queue", SWAGGER_ROLE_ADMIN),
)
async def list_verifications(
    _: RequireVerificationRead,
    status: Literal["pending", "verified", "rejected"] = "pending",
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> VerificationQueue:
    return await verification_service.list_queue(status, limit, offset)


@router.post(
    PATH_ADMIN_WORKER_VERIFICATION,
    response_model=WorkerProfileResponse,
    summary=swagger_summary("Verify / reject worker", SWAGGER_ROLE_ADMIN),
)
async def decide_worker(
    worker_profile_id: UUID, body: VerificationDecision, user: RequireVerificationWrite
) -> WorkerProfileResponse:
    return await verification_service.decide_worker(user, worker_profile_id, body)


@router.post(
    PATH_ADMIN_BUSINESS_VERIFICATION,
    response_model=BusinessProfileResponse,
    summary=swagger_summary("Verify / reject business", SWAGGER_ROLE_ADMIN),
)
async def decide_business(
    business_profile_id: UUID, body: VerificationDecision, user: RequireVerificationWrite
) -> BusinessProfileResponse:
    return await verification_service.decide_business(user, business_profile_id, body)
