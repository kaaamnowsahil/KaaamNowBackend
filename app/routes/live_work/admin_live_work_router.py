"""Admin: Live Work Pricing & Charges (audited) and the Live bookings / refunds monitor."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.constants.live_work.live_work_route_strings import (
    ADMIN_LIVE_WORK_PREFIX,
    OPENAPI_TAG_ADMIN_LIVE_WORK,
    PATH_ADMIN_BOOKING,
    PATH_ADMIN_BOOKINGS,
    PATH_ADMIN_PRICING,
    PATH_ADMIN_PRICING_AUDIT,
    PATH_ADMIN_REFUND_RETRY,
    PATH_ADMIN_REFUNDS,
)
from app.dependencies import (
    RequireLivePricingRead,
    RequireLivePricingWrite,
    RequireVerificationRead,
    RequireVerificationWrite,
)
from app.schemas.live_work.live_work_schemas import (
    AdminLiveBookingDetail,
    AdminLiveBookingPage,
    AdminLiveRefund,
    AdminLiveRefundPage,
    LivePricingAuditPage,
    LivePricingSettingsUpdate,
    LivePricingSettingsView,
)
from app.services.live_work import live_pricing_settings_service, live_work_admin_service

router = APIRouter(prefix=ADMIN_LIVE_WORK_PREFIX, tags=[OPENAPI_TAG_ADMIN_LIVE_WORK])


@router.get(
    PATH_ADMIN_PRICING,
    response_model=LivePricingSettingsView,
    summary=swagger_summary("Live Work Pricing & Charges", SWAGGER_ROLE_ADMIN),
)
async def get_pricing(_: RequireLivePricingRead) -> LivePricingSettingsView:
    return await live_pricing_settings_service.get_settings()


@router.put(
    PATH_ADMIN_PRICING,
    response_model=LivePricingSettingsView,
    summary=swagger_summary("Update Live Work Pricing & Charges", SWAGGER_ROLE_ADMIN),
)
async def update_pricing(
    body: LivePricingSettingsUpdate, admin: RequireLivePricingWrite
) -> LivePricingSettingsView:
    return await live_pricing_settings_service.update_settings(admin, body)


@router.get(
    PATH_ADMIN_PRICING_AUDIT,
    response_model=LivePricingAuditPage,
    summary=swagger_summary("Live Work pricing change history", SWAGGER_ROLE_ADMIN),
)
async def pricing_audit(
    _: RequireLivePricingRead,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> LivePricingAuditPage:
    return await live_pricing_settings_service.list_audit(limit, offset)


@router.get(
    PATH_ADMIN_BOOKINGS,
    response_model=AdminLiveBookingPage,
    summary=swagger_summary("Live Work bookings", SWAGGER_ROLE_ADMIN),
)
async def list_bookings(
    _: RequireVerificationRead,
    status: str | None = Query(default=None, max_length=32),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> AdminLiveBookingPage:
    return await live_work_admin_service.list_bookings(status, limit, offset)


@router.get(
    PATH_ADMIN_BOOKING,
    response_model=AdminLiveBookingDetail,
    summary=swagger_summary("Live Work booking detail", SWAGGER_ROLE_ADMIN),
)
async def booking_detail(booking_id: UUID, _: RequireVerificationRead) -> AdminLiveBookingDetail:
    return await live_work_admin_service.booking_detail(booking_id)


@router.get(
    PATH_ADMIN_REFUNDS,
    response_model=AdminLiveRefundPage,
    summary=swagger_summary("Live Work refunds", SWAGGER_ROLE_ADMIN),
)
async def list_refunds(
    _: RequireVerificationRead,
    status: Literal["pending", "processed", "failed"] | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> AdminLiveRefundPage:
    return await live_work_admin_service.list_refunds(status, limit, offset)


@router.post(
    PATH_ADMIN_REFUND_RETRY,
    response_model=AdminLiveRefund,
    summary=swagger_summary("Retry a Live Work refund", SWAGGER_ROLE_ADMIN),
)
async def retry_refund(refund_id: UUID, _: RequireVerificationWrite) -> AdminLiveRefund:
    return await live_work_admin_service.retry_refund(refund_id)
