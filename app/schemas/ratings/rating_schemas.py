"""Figma "Rate Aarav" / "Rate Cafe Bloom" (stars, chips, optional review)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.constants.ratings.rating_route_strings import MAX_TAGS, REVIEW_MAX_LENGTH
from app.schemas.shifts.assignment_schemas import RatingView


class RatingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stars: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    review: str = Field(default="", max_length=REVIEW_MAX_LENGTH)


class AssignmentRatings(BaseModel):
    items: list[RatingView]
    can_rate: bool
    my_direction: str
