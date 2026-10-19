"""Business: post and manage shifts, live search, applicants, roster."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.constants.application.application_common import SWAGGER_ROLE_BUSINESS, swagger_summary
from app.constants.shifts.shift_route_strings import (
    BUSINESS_ROUTE_PREFIX,
    OPENAPI_TAG_BUSINESS_SHIFTS,
    PATH_APPLICATION_REJECT,
    PATH_APPLICATION_SELECT,
    PATH_BUSINESS_ASSIGNMENT_CANCEL,
    PATH_DASHBOARD,
    PATH_SHIFT,
    PATH_SHIFT_APPLICATIONS,
    PATH_SHIFT_CANCEL,
    PATH_SHIFT_CONVERT,
    PATH_SHIFT_ESTIMATE,
    PATH_SHIFT_LIVE_SEARCH,
    PATH_SHIFT_PUBLISH,
    PATH_SHIFT_RETRY_LIVE,
    PATH_SHIFT_ROSTER,
    PATH_SHIFTS,
)
from app.dependencies import RequireShiftsRead, RequireShiftsWrite
from app.schemas.shifts.application_schemas import ApplicantList, ApplicationResponse
from app.schemas.shifts.assignment_schemas import (
    AssignmentCancelRequest,
    AssignmentCancelResponse,
    Roster,
)
from app.schemas.shifts.shift_schemas import (
    ConvertToScheduledRequest,
    DashboardResponse,
    LiveSearchStatus,
    ShiftCancelRequest,
    ShiftCostEstimate,
    ShiftCreate,
    ShiftEstimateRequest,
    ShiftPage,
    ShiftPatch,
    ShiftResponse,
    ShiftStatus,
    ShiftType,
)
from app.services.shifts import application_service, assignment_service, shift_service
from app.services.shifts.assignment_service import PARTY_BUSINESS

router = APIRouter(prefix=BUSINESS_ROUTE_PREFIX, tags=[OPENAPI_TAG_BUSINESS_SHIFTS])


@router.get(
    PATH_DASHBOARD,
    response_model=DashboardResponse,
    summary=swagger_summary("Business home (Live now / Scheduled)", SWAGGER_ROLE_BUSINESS),
)
async def dashboard(
    user: RequireShiftsRead, tab: Literal["live", "scheduled"] = "live"
) -> DashboardResponse:
    return await shift_service.dashboard(user, tab)


@router.post(
    PATH_SHIFT_ESTIMATE,
    response_model=ShiftCostEstimate,
    summary=swagger_summary("Estimate shift cost", SWAGGER_ROLE_BUSINESS),
)
async def estimate(body: ShiftEstimateRequest, _: RequireShiftsRead) -> ShiftCostEstimate:
    return await shift_service.estimate(body)


@router.post(
    PATH_SHIFTS,
    response_model=ShiftResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Create shift (optionally publish)", SWAGGER_ROLE_BUSINESS),
)
async def create_shift(body: ShiftCreate, user: RequireShiftsWrite) -> ShiftResponse:
    return await shift_service.create_shift(user, body)


@router.get(
    PATH_SHIFTS,
    response_model=ShiftPage,
    summary=swagger_summary("List my shifts", SWAGGER_ROLE_BUSINESS),
)
async def list_shifts(
    user: RequireShiftsRead,
    shift_type: ShiftType | None = None,
    status_in: list[ShiftStatus] | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> ShiftPage:
    return await shift_service.list_shifts(
        user, shift_type=shift_type, statuses=status_in, limit=limit, offset=offset
    )


@router.get(
    PATH_SHIFT,
    response_model=ShiftResponse,
    summary=swagger_summary("Get shift", SWAGGER_ROLE_BUSINESS),
)
async def get_shift(shift_id: UUID, user: RequireShiftsRead) -> ShiftResponse:
    return await shift_service.get_shift(user, shift_id)


@router.patch(
    PATH_SHIFT,
    response_model=ShiftResponse,
    summary=swagger_summary("Edit draft shift", SWAGGER_ROLE_BUSINESS),
)
async def update_shift(shift_id: UUID, body: ShiftPatch, user: RequireShiftsWrite) -> ShiftResponse:
    return await shift_service.update_draft(user, shift_id, body)


@router.post(
    PATH_SHIFT_PUBLISH,
    response_model=ShiftResponse,
    summary=swagger_summary("Publish shift", SWAGGER_ROLE_BUSINESS),
)
async def publish(shift_id: UUID, user: RequireShiftsWrite) -> ShiftResponse:
    return await shift_service.publish(user, shift_id)


@router.post(
    PATH_SHIFT_CANCEL,
    response_model=ShiftResponse,
    summary=swagger_summary("Cancel shift", SWAGGER_ROLE_BUSINESS),
)
async def cancel(
    shift_id: UUID, body: ShiftCancelRequest, user: RequireShiftsWrite
) -> ShiftResponse:
    return await shift_service.cancel(user, shift_id, body)


@router.post(
    PATH_SHIFT_CONVERT,
    response_model=ShiftResponse,
    summary=swagger_summary("Convert live search to scheduled", SWAGGER_ROLE_BUSINESS),
)
async def convert(
    shift_id: UUID, body: ConvertToScheduledRequest, user: RequireShiftsWrite
) -> ShiftResponse:
    return await shift_service.convert_to_scheduled(user, shift_id, body)


@router.post(
    PATH_SHIFT_RETRY_LIVE,
    response_model=ShiftResponse,
    summary=swagger_summary("Retry expired live search", SWAGGER_ROLE_BUSINESS),
)
async def retry_live(shift_id: UUID, user: RequireShiftsWrite) -> ShiftResponse:
    return await shift_service.retry_live(user, shift_id)


@router.get(
    PATH_SHIFT_LIVE_SEARCH,
    response_model=LiveSearchStatus,
    summary=swagger_summary("Live search progress", SWAGGER_ROLE_BUSINESS),
)
async def live_search(shift_id: UUID, user: RequireShiftsRead) -> LiveSearchStatus:
    return await shift_service.live_search_status(user, shift_id)


@router.get(
    PATH_SHIFT_ROSTER,
    response_model=Roster,
    summary=swagger_summary("Confirmed roster", SWAGGER_ROLE_BUSINESS),
)
async def roster(shift_id: UUID, user: RequireShiftsRead) -> Roster:
    return await assignment_service.roster(user, shift_id)


@router.get(
    PATH_SHIFT_APPLICATIONS,
    response_model=ApplicantList,
    summary=swagger_summary("Review applicants", SWAGGER_ROLE_BUSINESS),
)
async def applicants(
    shift_id: UUID,
    user: RequireShiftsRead,
    status_in: list[
        Literal["applied", "selected", "confirmed", "declined", "rejected", "withdrawn", "expired"]
    ]
    | None = Query(default=None, alias="status"),
) -> ApplicantList:
    return await application_service.list_applicants(user, shift_id, status_in)


@router.post(
    PATH_APPLICATION_SELECT,
    response_model=ApplicationResponse,
    summary=swagger_summary("Select applicant", SWAGGER_ROLE_BUSINESS),
)
async def select(application_id: UUID, user: RequireShiftsWrite) -> ApplicationResponse:
    return await application_service.select(user, application_id)


@router.post(
    PATH_APPLICATION_REJECT,
    response_model=ApplicationResponse,
    summary=swagger_summary("Reject applicant", SWAGGER_ROLE_BUSINESS),
)
async def reject(application_id: UUID, user: RequireShiftsWrite) -> ApplicationResponse:
    return await application_service.reject(user, application_id)


@router.post(
    PATH_BUSINESS_ASSIGNMENT_CANCEL,
    response_model=AssignmentCancelResponse,
    summary=swagger_summary("Remove booked worker", SWAGGER_ROLE_BUSINESS),
)
async def cancel_assignment(
    assignment_id: UUID, body: AssignmentCancelRequest, user: RequireShiftsWrite
) -> AssignmentCancelResponse:
    return await assignment_service.cancel(user, assignment_id, body, as_party=PARTY_BUSINESS)
