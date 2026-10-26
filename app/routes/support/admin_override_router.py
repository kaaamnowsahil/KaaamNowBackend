"""Admin: per-booking ledger and fee / strike / voucher overrides with a reason."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.constants.support.support_route_strings import (
    ADMIN_SUPPORT_ROUTE_PREFIX,
    OPENAPI_TAG_ADMIN_SUPPORT,
    PATH_BOOKING_LEDGER,
    PATH_BOOKING_OVERRIDES,
)
from app.dependencies import RequireVerificationRead, RequireVerificationWrite
from app.schemas.support.support_schemas import BookingLedger, OverrideRequest, OverrideView
from app.services.support import override_service

router = APIRouter(prefix=ADMIN_SUPPORT_ROUTE_PREFIX, tags=[OPENAPI_TAG_ADMIN_SUPPORT])


@router.get(
    PATH_BOOKING_LEDGER,
    response_model=BookingLedger,
    summary=swagger_summary("Booking ledger", SWAGGER_ROLE_ADMIN),
)
async def booking_ledger(assignment_id: UUID, _: RequireVerificationRead) -> BookingLedger:
    return await override_service.get_ledger(assignment_id)


@router.post(
    PATH_BOOKING_OVERRIDES,
    response_model=OverrideView,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Override booking fee / strike / voucher", SWAGGER_ROLE_ADMIN),
)
async def apply_override(
    assignment_id: UUID, body: OverrideRequest, admin: RequireVerificationWrite
) -> OverrideView:
    return await override_service.apply_override(admin, assignment_id, body)
