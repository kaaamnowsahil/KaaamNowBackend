"""Two-way rating route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ASSIGNMENTS

RATINGS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ASSIGNMENTS}"
OPENAPI_TAG_RATINGS: Final[str] = "ratings"

PATH_ASSIGNMENT_RATINGS: Final[str] = "/{assignment_id}/ratings"

REVIEW_MAX_LENGTH: Final[int] = 1000
MAX_TAGS: Final[int] = 8

MSG_RATING_NOT_ALLOWED: Final[str] = "You can rate only after the shift is checked out."
MSG_ALREADY_RATED: Final[str] = "You have already rated this shift."
MSG_INVALID_TAGS: Final[str] = "One or more tags are not valid for this rating."
