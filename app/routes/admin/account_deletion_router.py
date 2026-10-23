"""Admin review and retention holds for account-deletion requests."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.constants.admin.account_deletion_route_strings import (
    ADMIN_DELETION_ROUTE_PREFIX,
    PATH_DELETION_APPROVE,
    PATH_DELETION_HOLD,
    PATH_DELETION_HOLDS,
    PATH_DELETION_REQUEST,
    PATH_DELETION_REQUESTS,
)
from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.dependencies import RequireVerificationRead, RequireVerificationWrite
from app.schemas.users.deletion_schemas import (
    AccountDeletionHoldCreate,
    AccountDeletionRequestPage,
    AdminAccountDeletionRequestDetail,
)
from app.services.users import deletion_service

router = APIRouter(prefix=ADMIN_DELETION_ROUTE_PREFIX, tags=["admin account deletion"])


@router.get(
    PATH_DELETION_REQUESTS,
    response_model=AccountDeletionRequestPage,
    summary=swagger_summary("List account deletion requests", SWAGGER_ROLE_ADMIN),
)
async def list_deletion_requests(
    _: RequireVerificationRead,
    status: Literal["pending", "approved", "on_hold", "completed"] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountDeletionRequestPage:
    return await deletion_service.list_requests(
        status_filter=status, limit=limit, offset=offset
    )


@router.get(
    PATH_DELETION_REQUEST,
    response_model=AdminAccountDeletionRequestDetail,
    summary=swagger_summary("Get account deletion request", SWAGGER_ROLE_ADMIN),
)
async def get_deletion_request(
    request_id: UUID, _: RequireVerificationRead
) -> AdminAccountDeletionRequestDetail:
    return await deletion_service.get_admin_request(request_id)


@router.post(
    PATH_DELETION_APPROVE,
    response_model=AdminAccountDeletionRequestDetail,
    summary=swagger_summary("Approve account deletion request", SWAGGER_ROLE_ADMIN),
)
async def approve_deletion_request(
    request_id: UUID, user: RequireVerificationWrite
) -> AdminAccountDeletionRequestDetail:
    return await deletion_service.approve_request(request_id, user)


@router.post(
    PATH_DELETION_HOLDS,
    response_model=AdminAccountDeletionRequestDetail,
    summary=swagger_summary("Add a documented account deletion hold", SWAGGER_ROLE_ADMIN),
)
async def add_deletion_hold(
    request_id: UUID, body: AccountDeletionHoldCreate, user: RequireVerificationWrite
) -> AdminAccountDeletionRequestDetail:
    return await deletion_service.add_hold(request_id, body, user)


@router.delete(
    PATH_DELETION_HOLD,
    response_model=AdminAccountDeletionRequestDetail,
    summary=swagger_summary("Release an account deletion hold", SWAGGER_ROLE_ADMIN),
)
async def release_deletion_hold(
    request_id: UUID, hold_id: UUID, user: RequireVerificationWrite
) -> AdminAccountDeletionRequestDetail:
    return await deletion_service.release_hold(request_id, hold_id, user)
