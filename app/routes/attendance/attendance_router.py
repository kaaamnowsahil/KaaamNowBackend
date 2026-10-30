"""Worker check-in / check-out; business attendance review and no-show."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.constants.application.application_common import (
    SWAGGER_ROLE_BUSINESS,
    SWAGGER_ROLE_WORKER,
    swagger_summary,
)
from app.constants.attendance.attendance_route_strings import (
    BUSINESS_ROUTE_PREFIX,
    OPENAPI_TAG_ATTENDANCE,
    PATH_APPROVE,
    PATH_CHECK_IN,
    PATH_CHECK_OUT,
    PATH_COMPLETION_CODE_REISSUE,
    PATH_EARLY_END,
    PATH_EARLY_END_REQUEST,
    PATH_END,
    PATH_EXTENSION_ACCEPT,
    PATH_EXTENSION_DECLINE,
    PATH_EXTENSIONS,
    PATH_NO_SHOW,
    PATH_STOP_WORK,
    WORKER_ROUTE_PREFIX,
)
from app.dependencies import RequireShiftsWrite, RequireWorkWrite
from app.schemas.attendance.attendance_schemas import (
    AttendanceApproveRequest,
    CheckInRequest,
    CheckOutRequest,
    EarlyEndRequest,
    ExtensionRequest,
    ExtensionView,
    StopWorkRequest,
)
from app.schemas.shifts.assignment_schemas import AssignmentDetail
from app.services.attendance import attendance_service
from app.services.shifts.assignment_service import PARTY_BUSINESS, PARTY_WORKER

worker_router = APIRouter(prefix=WORKER_ROUTE_PREFIX, tags=[OPENAPI_TAG_ATTENDANCE])
business_router = APIRouter(prefix=BUSINESS_ROUTE_PREFIX, tags=[OPENAPI_TAG_ATTENDANCE])


@worker_router.post(
    PATH_CHECK_IN,
    response_model=AssignmentDetail,
    summary=swagger_summary("Check in (location + site code)", SWAGGER_ROLE_WORKER),
)
async def check_in(
    assignment_id: UUID, body: CheckInRequest, user: RequireWorkWrite
) -> AssignmentDetail:
    return await attendance_service.check_in(user, assignment_id, body)


@worker_router.post(
    PATH_CHECK_OUT,
    response_model=AssignmentDetail,
    summary=swagger_summary("Check out", SWAGGER_ROLE_WORKER),
)
async def check_out(
    assignment_id: UUID, body: CheckOutRequest, user: RequireWorkWrite
) -> AssignmentDetail:
    return await attendance_service.check_out(user, assignment_id, body)


@business_router.post(
    PATH_APPROVE,
    response_model=AssignmentDetail,
    summary=swagger_summary("Approve attendance", SWAGGER_ROLE_BUSINESS),
)
async def approve(
    assignment_id: UUID, body: AttendanceApproveRequest, user: RequireShiftsWrite
) -> AssignmentDetail:
    return await attendance_service.approve(user, assignment_id, body)


@business_router.post(
    PATH_NO_SHOW,
    response_model=AssignmentDetail,
    summary=swagger_summary("Mark no-show", SWAGGER_ROLE_BUSINESS),
)
async def no_show(assignment_id: UUID, user: RequireShiftsWrite) -> AssignmentDetail:
    return await attendance_service.mark_no_show(user, assignment_id)


@worker_router.post(
    PATH_EARLY_END_REQUEST,
    response_model=AssignmentDetail,
    summary=swagger_summary("Ask business for early-end PIN", SWAGGER_ROLE_WORKER),
)
async def worker_request_early_end(assignment_id: UUID, user: RequireWorkWrite) -> AssignmentDetail:
    return await attendance_service.request_early_end(user, assignment_id, as_party=PARTY_WORKER)


@worker_router.post(
    PATH_EARLY_END,
    response_model=AssignmentDetail,
    summary=swagger_summary("End early with PIN", SWAGGER_ROLE_WORKER),
)
async def worker_end_early(
    assignment_id: UUID, body: EarlyEndRequest, user: RequireWorkWrite
) -> AssignmentDetail:
    return await attendance_service.end_early(user, assignment_id, body, as_party=PARTY_WORKER)


@worker_router.post(
    PATH_EXTENSION_ACCEPT,
    response_model=AssignmentDetail,
    summary=swagger_summary("Accept extension", SWAGGER_ROLE_WORKER),
)
async def accept_extension(
    assignment_id: UUID, extension_id: UUID, user: RequireWorkWrite
) -> AssignmentDetail:
    return await attendance_service.respond_extension(
        user, assignment_id, extension_id, accept=True
    )


@worker_router.post(
    PATH_EXTENSION_DECLINE,
    response_model=AssignmentDetail,
    summary=swagger_summary("Decline extension", SWAGGER_ROLE_WORKER),
)
async def decline_extension(
    assignment_id: UUID, extension_id: UUID, user: RequireWorkWrite
) -> AssignmentDetail:
    return await attendance_service.respond_extension(
        user, assignment_id, extension_id, accept=False
    )


@business_router.post(
    PATH_END,
    response_model=AssignmentDetail,
    summary=swagger_summary("End shift", SWAGGER_ROLE_BUSINESS),
)
async def business_end(assignment_id: UUID, user: RequireShiftsWrite) -> AssignmentDetail:
    return await attendance_service.business_end(user, assignment_id)


@business_router.post(
    PATH_COMPLETION_CODE_REISSUE,
    response_model=AssignmentDetail,
    summary=swagger_summary("Issue a new completion code", SWAGGER_ROLE_BUSINESS),
)
async def reissue_completion_code(
    assignment_id: UUID, user: RequireShiftsWrite
) -> AssignmentDetail:
    return await attendance_service.reissue_completion_code(user, assignment_id)


@business_router.post(
    PATH_EARLY_END_REQUEST,
    response_model=AssignmentDetail,
    summary=swagger_summary("Ask worker for early-end PIN", SWAGGER_ROLE_BUSINESS),
)
async def business_request_early_end(
    assignment_id: UUID, user: RequireShiftsWrite
) -> AssignmentDetail:
    return await attendance_service.request_early_end(user, assignment_id, as_party=PARTY_BUSINESS)


@business_router.post(
    PATH_EARLY_END,
    response_model=AssignmentDetail,
    summary=swagger_summary("End early with PIN", SWAGGER_ROLE_BUSINESS),
)
async def business_end_early(
    assignment_id: UUID, body: EarlyEndRequest, user: RequireShiftsWrite
) -> AssignmentDetail:
    return await attendance_service.end_early(user, assignment_id, body, as_party=PARTY_BUSINESS)


@business_router.post(
    PATH_STOP_WORK,
    response_model=AssignmentDetail,
    summary=swagger_summary("Stop work", SWAGGER_ROLE_BUSINESS),
)
async def stop_work(
    assignment_id: UUID, body: StopWorkRequest, user: RequireShiftsWrite
) -> AssignmentDetail:
    return await attendance_service.stop_work(user, assignment_id, body)


@business_router.post(
    PATH_EXTENSIONS,
    response_model=ExtensionView,
    status_code=201,
    summary=swagger_summary("Request extension", SWAGGER_ROLE_BUSINESS),
)
async def request_extension(
    assignment_id: UUID, body: ExtensionRequest, user: RequireShiftsWrite
) -> ExtensionView:
    return await attendance_service.request_extension(user, assignment_id, body)
