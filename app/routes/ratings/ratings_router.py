"""Ratings on a shift assignment (both parties)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.constants.application.application_common import SWAGGER_ROLE_PARTICIPANT, swagger_summary
from app.constants.ratings.rating_route_strings import (
    OPENAPI_TAG_RATINGS,
    PATH_ASSIGNMENT_RATINGS,
    RATINGS_ROUTE_PREFIX,
)
from app.dependencies import CurrentUser
from app.schemas.ratings.rating_schemas import AssignmentRatings, RatingCreate
from app.schemas.shifts.assignment_schemas import RatingView
from app.services.ratings import rating_service

router = APIRouter(prefix=RATINGS_ROUTE_PREFIX, tags=[OPENAPI_TAG_RATINGS])


@router.get(
    PATH_ASSIGNMENT_RATINGS,
    response_model=AssignmentRatings,
    summary=swagger_summary("Ratings for a shift", SWAGGER_ROLE_PARTICIPANT),
)
async def list_ratings(assignment_id: UUID, user: CurrentUser) -> AssignmentRatings:
    return await rating_service.list_ratings(user, assignment_id)


@router.post(
    PATH_ASSIGNMENT_RATINGS,
    response_model=RatingView,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Rate the other party", SWAGGER_ROLE_PARTICIPANT),
)
async def rate(assignment_id: UUID, body: RatingCreate, user: CurrentUser) -> RatingView:
    return await rating_service.rate(user, assignment_id, body)
