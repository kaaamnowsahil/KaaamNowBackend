"""Worker: Live Work requests, accept/decline, travel, start with arrival code, complete."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.constants.application.application_common import SWAGGER_ROLE_WORKER, swagger_summary
from app.constants.live_work.live_work_route_strings import (
    OPENAPI_TAG_WORKER_LIVE_WORK,
    PATH_ACTIVE,
    PATH_REQUEST_ACCEPT,
    PATH_REQUEST_DECLINE,
    PATH_REQUESTS,
    PATH_WORKER_BOOKING,
    PATH_WORKER_BOOKINGS,
    PATH_WORKER_CANCEL,
    PATH_WORKER_CANCEL_PREVIEW,
    PATH_WORKER_COMPLETE,
    PATH_WORKER_EXTENSION_ANSWER,
    PATH_WORKER_LOCATION,
    PATH_WORKER_START,
    PATH_WORKER_START_TRAVEL,
    WORKER_LIVE_WORK_PREFIX,
)
from app.dependencies import RequireWorkRead, RequireWorkWrite
from app.schemas.live_work.live_work_schemas import (
    LiveCancelPreview,
    LiveCancelRequest,
    LiveExtensionAnswer,
    LiveLocationUpdate,
    LiveStartWork,
    WorkerActiveLiveWork,
    WorkerLiveBooking,
    WorkerLiveRequest,
)
from app.services.live_work import live_worker_service

router = APIRouter(prefix=WORKER_LIVE_WORK_PREFIX, tags=[OPENAPI_TAG_WORKER_LIVE_WORK])


@router.get(
    PATH_REQUESTS,
    response_model=list[WorkerLiveRequest],
    summary=swagger_summary("Live Work requests for me", SWAGGER_ROLE_WORKER),
)
async def list_requests(user: RequireWorkRead) -> list[WorkerLiveRequest]:
    return await live_worker_service.list_requests(user)


@router.post(
    PATH_REQUEST_ACCEPT,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Accept Live Work", SWAGGER_ROLE_WORKER),
)
async def accept(booking_id: UUID, user: RequireWorkWrite) -> WorkerLiveBooking:
    return await live_worker_service.accept(user, booking_id)


@router.post(
    PATH_REQUEST_DECLINE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Decline Live Work", SWAGGER_ROLE_WORKER),
)
async def decline(booking_id: UUID, user: RequireWorkWrite) -> Response:
    await live_worker_service.decline(user, booking_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    PATH_ACTIVE,
    response_model=WorkerActiveLiveWork,
    summary=swagger_summary("My current Live Work", SWAGGER_ROLE_WORKER),
)
async def active(user: RequireWorkRead) -> WorkerActiveLiveWork:
    return await live_worker_service.active(user)


@router.get(
    PATH_WORKER_BOOKINGS,
    response_model=list[WorkerLiveBooking],
    summary=swagger_summary("My Live Work history", SWAGGER_ROLE_WORKER),
)
async def history(
    user: RequireWorkRead,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[WorkerLiveBooking]:
    return await live_worker_service.history(user, limit, offset)


@router.get(
    PATH_WORKER_BOOKING,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Live Work status", SWAGGER_ROLE_WORKER),
)
async def get_booking(assignment_id: UUID, user: RequireWorkRead) -> WorkerLiveBooking:
    return await live_worker_service.get_booking(user, assignment_id)


@router.post(
    PATH_WORKER_START_TRAVEL,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("On my way", SWAGGER_ROLE_WORKER),
)
async def start_travel(assignment_id: UUID, user: RequireWorkWrite) -> WorkerLiveBooking:
    return await live_worker_service.start_travel(user, assignment_id)


@router.post(
    PATH_WORKER_LOCATION,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Share my location", SWAGGER_ROLE_WORKER),
)
async def update_location(
    assignment_id: UUID, body: LiveLocationUpdate, user: RequireWorkWrite
) -> WorkerLiveBooking:
    return await live_worker_service.update_location(user, assignment_id, body)


@router.post(
    PATH_WORKER_START,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Start Work with the arrival code", SWAGGER_ROLE_WORKER),
)
async def start_work(
    assignment_id: UUID, body: LiveStartWork, user: RequireWorkWrite
) -> WorkerLiveBooking:
    return await live_worker_service.start_work(user, assignment_id, body)


@router.post(
    PATH_WORKER_COMPLETE,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Complete Work", SWAGGER_ROLE_WORKER),
)
async def complete(assignment_id: UUID, user: RequireWorkWrite) -> WorkerLiveBooking:
    return await live_worker_service.complete(user, assignment_id)


@router.get(
    PATH_WORKER_CANCEL_PREVIEW,
    response_model=LiveCancelPreview,
    summary=swagger_summary("Preview cancelling", SWAGGER_ROLE_WORKER),
)
async def cancel_preview(assignment_id: UUID, user: RequireWorkRead) -> LiveCancelPreview:
    return await live_worker_service.cancel_preview(user, assignment_id)


@router.post(
    PATH_WORKER_CANCEL,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Cancel Live Work", SWAGGER_ROLE_WORKER),
)
async def cancel(
    assignment_id: UUID, body: LiveCancelRequest, user: RequireWorkWrite
) -> WorkerLiveBooking:
    return await live_worker_service.cancel(user, assignment_id, body)


@router.post(
    PATH_WORKER_EXTENSION_ANSWER,
    response_model=WorkerLiveBooking,
    summary=swagger_summary("Accept or decline extra time", SWAGGER_ROLE_WORKER),
)
async def answer_extension(
    assignment_id: UUID, extension_id: UUID, body: LiveExtensionAnswer, user: RequireWorkWrite
) -> WorkerLiveBooking:
    return await live_worker_service.answer_extension(user, assignment_id, extension_id, body)
