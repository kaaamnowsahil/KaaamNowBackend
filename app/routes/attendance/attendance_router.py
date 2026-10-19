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
    PATH_NO_SHOW,
    WORKER_ROUTE_PREFIX,
)
from app.dependencies import RequireShiftsWrite, RequireWorkWrite
from app.schemas.attendance.attendance_schemas import (
    AttendanceApproveRequest,
    CheckInRequest,
    CheckOutRequest,
)
from app.schemas.shifts.assignment_schemas import AssignmentDetail
from app.services.attendance import attendance_service

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
