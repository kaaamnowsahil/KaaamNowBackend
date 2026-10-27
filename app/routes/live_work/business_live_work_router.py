"""Business / Work: post, pay, track, extend, cancel and end Live Work."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.constants.application.application_common import SWAGGER_ROLE_BUSINESS, swagger_summary
from app.constants.live_work.live_work_route_strings import (
    BUSINESS_LIVE_WORK_PREFIX,
    OPENAPI_TAG_BUSINESS_LIVE_WORK,
    PATH_AVAILABLE_WORKERS,
    PATH_BOOKING,
    PATH_BOOKING_ARRIVAL_CODE,
    PATH_BOOKING_CANCEL,
    PATH_BOOKING_CANCEL_PREVIEW,
    PATH_BOOKING_END,
    PATH_BOOKING_EXTENSION_CANCEL,
    PATH_BOOKING_EXTENSION_QUOTE,
    PATH_BOOKING_EXTENSIONS,
    PATH_BOOKINGS,
    PATH_QUOTE,
)
from app.dependencies import RequireShiftsRead, RequireShiftsWrite
from app.schemas.live_work.live_work_schemas import (
    BusinessLiveBooking,
    BusinessLiveBookingPage,
    LiveAvailableWorkers,
    LiveCancelPreview,
    LiveCancelRequest,
    LiveExtensionCreate,
    LiveExtensionQuote,
    LivePriceBreakdown,
    LiveWorkCreate,
    LiveWorkQuoteRequest,
)
from app.services.live_work import live_work_service

router = APIRouter(prefix=BUSINESS_LIVE_WORK_PREFIX, tags=[OPENAPI_TAG_BUSINESS_LIVE_WORK])


@router.post(
    PATH_QUOTE,
    response_model=LivePriceBreakdown,
    summary=swagger_summary("Price a Live Work request", SWAGGER_ROLE_BUSINESS),
)
async def quote(body: LiveWorkQuoteRequest, user: RequireShiftsRead) -> LivePriceBreakdown:
    return await live_work_service.quote(user, body)


@router.get(
    PATH_AVAILABLE_WORKERS,
    response_model=LiveAvailableWorkers,
    summary=swagger_summary("Available Workers nearby", SWAGGER_ROLE_BUSINESS),
)
async def available_workers(
    user: RequireShiftsRead,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    category: str | None = Query(default=None, max_length=64),
) -> LiveAvailableWorkers:
    return await live_work_service.available_workers(
        user, category_slug=category, latitude=lat, longitude=lng
    )


@router.post(
    PATH_BOOKINGS,
    response_model=BusinessLiveBooking,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Post Live Work", SWAGGER_ROLE_BUSINESS),
)
async def create(body: LiveWorkCreate, user: RequireShiftsWrite) -> BusinessLiveBooking:
    return await live_work_service.create(user, body)


@router.get(
    PATH_BOOKINGS,
    response_model=BusinessLiveBookingPage,
    summary=swagger_summary("My Live Work", SWAGGER_ROLE_BUSINESS),
)
async def list_bookings(
    user: RequireShiftsRead,
    active: bool = False,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> BusinessLiveBookingPage:
    return await live_work_service.list_bookings(
        user, active_only=active, limit=limit, offset=offset
    )


@router.get(
    PATH_BOOKING,
    response_model=BusinessLiveBooking,
    summary=swagger_summary("Live Work status", SWAGGER_ROLE_BUSINESS),
)
async def get_booking(booking_id: UUID, user: RequireShiftsRead) -> BusinessLiveBooking:
    return await live_work_service.get_booking(user, booking_id)


@router.get(
    PATH_BOOKING_CANCEL_PREVIEW,
    response_model=LiveCancelPreview,
    summary=swagger_summary("Preview cancelling Live Work", SWAGGER_ROLE_BUSINESS),
)
async def cancel_preview(booking_id: UUID, user: RequireShiftsRead) -> LiveCancelPreview:
    return await live_work_service.cancel_preview(user, booking_id)


@router.post(
    PATH_BOOKING_CANCEL,
    response_model=BusinessLiveBooking,
    summary=swagger_summary("Cancel Live Work", SWAGGER_ROLE_BUSINESS),
)
async def cancel(
    booking_id: UUID, body: LiveCancelRequest, user: RequireShiftsWrite
) -> BusinessLiveBooking:
    return await live_work_service.cancel(user, booking_id, body)


@router.get(
    PATH_BOOKING_EXTENSION_QUOTE,
    response_model=LiveExtensionQuote,
    summary=swagger_summary("Price extra time", SWAGGER_ROLE_BUSINESS),
)
async def extension_quote(
    booking_id: UUID, user: RequireShiftsRead, minutes: int = Query()
) -> LiveExtensionQuote:
    return await live_work_service.extension_quote(user, booking_id, minutes)


@router.post(
    PATH_BOOKING_EXTENSIONS,
    response_model=BusinessLiveBooking,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Request extra time", SWAGGER_ROLE_BUSINESS),
)
async def request_extension(
    booking_id: UUID, body: LiveExtensionCreate, user: RequireShiftsWrite
) -> BusinessLiveBooking:
    return await live_work_service.request_extension(user, booking_id, body)


@router.post(
    PATH_BOOKING_EXTENSION_CANCEL,
    response_model=BusinessLiveBooking,
    summary=swagger_summary("Withdraw an extra-time request", SWAGGER_ROLE_BUSINESS),
)
async def cancel_extension(
    booking_id: UUID, extension_id: UUID, user: RequireShiftsWrite
) -> BusinessLiveBooking:
    return await live_work_service.cancel_extension(user, booking_id, extension_id)


@router.post(
    PATH_BOOKING_END,
    response_model=BusinessLiveBooking,
    summary=swagger_summary("End Work now (reserved time is billed)", SWAGGER_ROLE_BUSINESS),
)
async def end_work(booking_id: UUID, user: RequireShiftsWrite) -> BusinessLiveBooking:
    return await live_work_service.end_work(user, booking_id)


@router.post(
    PATH_BOOKING_ARRIVAL_CODE,
    response_model=BusinessLiveBooking,
    summary=swagger_summary("New arrival code", SWAGGER_ROLE_BUSINESS),
)
async def reissue_arrival_code(booking_id: UUID, user: RequireShiftsWrite) -> BusinessLiveBooking:
    return await live_work_service.reissue_arrival_code(user, booking_id)
