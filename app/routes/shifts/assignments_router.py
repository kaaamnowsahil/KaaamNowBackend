"""Shared booking endpoints for the worker and the business on one assignment."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, status

from app.constants.application.application_common import SWAGGER_ROLE_PARTICIPANT, swagger_summary
from app.constants.shifts.shift_route_strings import (
    ASSIGNMENTS_ROUTE_PREFIX,
    OPENAPI_TAG_ASSIGNMENTS,
    PATH_ASSIGNMENT,
    PATH_ASSIGNMENT_CONTACT,
    PATH_ASSIGNMENT_MESSAGES,
    PATH_ASSIGNMENT_TRACKING,
)
from app.dependencies import CurrentUser
from app.schemas.shifts.assignment_schemas import (
    AssignmentDetail,
    ContactResponse,
    MessageCreate,
    MessageItem,
    TrackingResponse,
)
from app.services.shifts import assignment_service

router = APIRouter(prefix=ASSIGNMENTS_ROUTE_PREFIX, tags=[OPENAPI_TAG_ASSIGNMENTS])


@router.get(
    PATH_ASSIGNMENT,
    response_model=AssignmentDetail,
    summary=swagger_summary("Booking detail", SWAGGER_ROLE_PARTICIPANT),
)
async def get_assignment(assignment_id: UUID, user: CurrentUser) -> AssignmentDetail:
    return await assignment_service.get_assignment(user, assignment_id)


@router.get(
    PATH_ASSIGNMENT_TRACKING,
    response_model=TrackingResponse,
    summary=swagger_summary("Live worker location + ETA", SWAGGER_ROLE_PARTICIPANT),
)
async def tracking(assignment_id: UUID, user: CurrentUser) -> TrackingResponse:
    return await assignment_service.tracking(user, assignment_id)


@router.get(
    PATH_ASSIGNMENT_CONTACT,
    response_model=ContactResponse,
    summary=swagger_summary("Call the other party", SWAGGER_ROLE_PARTICIPANT),
)
async def contact(assignment_id: UUID, user: CurrentUser) -> ContactResponse:
    return await assignment_service.contact(user, assignment_id)


@router.get(
    PATH_ASSIGNMENT_MESSAGES,
    response_model=list[MessageItem],
    summary=swagger_summary("Chat messages", SWAGGER_ROLE_PARTICIPANT),
)
async def list_messages(
    assignment_id: UUID, user: CurrentUser, after: datetime | None = None
) -> list[MessageItem]:
    return await assignment_service.list_messages(user, assignment_id, after)


@router.post(
    PATH_ASSIGNMENT_MESSAGES,
    response_model=MessageItem,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Send chat message", SWAGGER_ROLE_PARTICIPANT),
)
async def send_message(assignment_id: UUID, body: MessageCreate, user: CurrentUser) -> MessageItem:
    return await assignment_service.send_message(user, assignment_id, body)
