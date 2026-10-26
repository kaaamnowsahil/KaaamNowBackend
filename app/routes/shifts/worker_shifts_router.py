"""Worker: discover shifts, applications, my shifts, travel, cancel; live on ``live_router``."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.constants.application.application_common import SWAGGER_ROLE_WORKER, swagger_summary
from app.constants.shifts.shift_route_strings import (
    OPENAPI_TAG_WORKER_LIVE,
    OPENAPI_TAG_WORKER_SHIFTS,
    PATH_APPLICATION_CONFIRM,
    PATH_APPLICATION_DECLINE,
    PATH_APPLICATION_WITHDRAW,
    PATH_APPLY,
    PATH_FEED,
    PATH_LIVE_ACCEPT,
    PATH_LIVE_DECLINE,
    PATH_LIVE_REQUESTS,
    PATH_MY_SHIFTS,
    PATH_START_TRAVEL,
    PATH_WORKER_ASSIGNMENT_CANCEL,
    PATH_WORKER_ASSIGNMENT_CANCEL_PREVIEW,
    PATH_WORKER_SHIFT,
    WORKER_ROUTE_PREFIX,
)
from app.dependencies import RequireWorkRead, RequireWorkWrite
from app.schemas.shifts.application_schemas import ApplicationCreate, ApplicationResponse
from app.schemas.shifts.assignment_schemas import (
    AssignmentCancelRequest,
    AssignmentCancelResponse,
    AssignmentDetail,
)
from app.schemas.shifts.shift_schemas import (
    CancellationQuote,
    FeedPage,
    LiveRequestItem,
    MyShiftsPage,
    ShiftType,
    WorkerShiftDetail,
)
from app.services.shifts import (
    application_service,
    assignment_service,
    live_dispatch_service,
    shift_feed_service,
)
from app.services.shifts.assignment_service import PARTY_WORKER

router = APIRouter(prefix=WORKER_ROUTE_PREFIX, tags=[OPENAPI_TAG_WORKER_SHIFTS])
live_router = APIRouter(prefix=WORKER_ROUTE_PREFIX, tags=[OPENAPI_TAG_WORKER_LIVE])


@router.get(
    PATH_FEED,
    response_model=FeedPage,
    summary=swagger_summary("Shifts near you", SWAGGER_ROLE_WORKER),
)
async def feed(
    user: RequireWorkRead,
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=50),
    shift_type: ShiftType | None = None,
    category: str | None = Query(default=None, max_length=64),
    business_type_slugs: str | None = Query(default=None, max_length=1024),
    q: str | None = Query(default=None, max_length=80),
    sort: Literal["distance", "starts_at", "pay"] = "distance",
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> FeedPage:
    return await shift_feed_service.feed(
        user,
        latitude=lat,
        longitude=lng,
        radius_km=radius_km,
        shift_type=shift_type,
        category_slug=category,
        business_type_slugs=(
            list(
                dict.fromkeys(
                    slug.strip() for slug in business_type_slugs.split(",") if slug.strip()
                )
            )
            if business_type_slugs
            else None
        ),
        query=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get(
    PATH_MY_SHIFTS,
    response_model=MyShiftsPage,
    summary=swagger_summary("My shifts", SWAGGER_ROLE_WORKER),
)
async def my_shifts(
    user: RequireWorkRead,
    tab: Literal["upcoming", "active", "completed", "applications"] = "upcoming",
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> MyShiftsPage:
    return await shift_feed_service.my_shifts(user, tab, limit, offset)


@live_router.get(
    PATH_LIVE_REQUESTS,
    response_model=list[LiveRequestItem],
    summary=swagger_summary("Open live requests", SWAGGER_ROLE_WORKER),
)
async def live_requests(user: RequireWorkRead) -> list[LiveRequestItem]:
    return await live_dispatch_service.list_live_requests(user)


@router.get(
    PATH_WORKER_SHIFT,
    response_model=WorkerShiftDetail,
    summary=swagger_summary("Shift detail", SWAGGER_ROLE_WORKER),
)
async def shift_detail(shift_id: UUID, user: RequireWorkRead) -> WorkerShiftDetail:
    return await shift_feed_service.get_shift(user, shift_id)


@live_router.post(
    PATH_LIVE_ACCEPT,
    response_model=AssignmentDetail,
    summary=swagger_summary("Accept live request", SWAGGER_ROLE_WORKER),
)
async def accept_live(shift_id: UUID, user: RequireWorkWrite) -> AssignmentDetail:
    return await live_dispatch_service.accept(user, shift_id)


@live_router.post(
    PATH_LIVE_DECLINE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Decline live request", SWAGGER_ROLE_WORKER),
)
async def decline_live(shift_id: UUID, user: RequireWorkWrite) -> None:
    await live_dispatch_service.decline(user, shift_id)


@router.post(
    PATH_APPLY,
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Apply to scheduled shift", SWAGGER_ROLE_WORKER),
)
async def apply(
    shift_id: UUID, body: ApplicationCreate, user: RequireWorkWrite
) -> ApplicationResponse:
    return await application_service.apply(user, shift_id, body)


@router.post(
    PATH_APPLICATION_WITHDRAW,
    response_model=ApplicationResponse,
    summary=swagger_summary("Withdraw application", SWAGGER_ROLE_WORKER),
)
async def withdraw(application_id: UUID, user: RequireWorkWrite) -> ApplicationResponse:
    return await application_service.withdraw(user, application_id)


@router.post(
    PATH_APPLICATION_CONFIRM,
    response_model=ApplicationResponse,
    summary=swagger_summary("Confirm selection", SWAGGER_ROLE_WORKER),
)
async def confirm(application_id: UUID, user: RequireWorkWrite) -> ApplicationResponse:
    return await application_service.confirm(user, application_id)


@router.post(
    PATH_APPLICATION_DECLINE,
    response_model=ApplicationResponse,
    summary=swagger_summary("Decline selection", SWAGGER_ROLE_WORKER),
)
async def decline_selection(application_id: UUID, user: RequireWorkWrite) -> ApplicationResponse:
    return await application_service.decline(user, application_id)


@router.post(
    PATH_START_TRAVEL,
    response_model=AssignmentDetail,
    summary=swagger_summary("Start travelling", SWAGGER_ROLE_WORKER),
)
async def start_travel(assignment_id: UUID, user: RequireWorkWrite) -> AssignmentDetail:
    return await assignment_service.start_travel(user, assignment_id)


@router.get(
    PATH_WORKER_ASSIGNMENT_CANCEL_PREVIEW,
    response_model=CancellationQuote,
    summary=swagger_summary("Cancellation fee preview for my booking", SWAGGER_ROLE_WORKER),
)
async def cancel_assignment_preview(
    assignment_id: UUID, user: RequireWorkRead
) -> CancellationQuote:
    return await assignment_service.cancel_preview(user, assignment_id, as_party=PARTY_WORKER)


@router.post(
    PATH_WORKER_ASSIGNMENT_CANCEL,
    response_model=AssignmentCancelResponse,
    summary=swagger_summary("Cancel my booking", SWAGGER_ROLE_WORKER),
)
async def cancel_assignment(
    assignment_id: UUID, body: AssignmentCancelRequest, user: RequireWorkWrite
) -> AssignmentCancelResponse:
    return await assignment_service.cancel(user, assignment_id, body, as_party=PARTY_WORKER)
