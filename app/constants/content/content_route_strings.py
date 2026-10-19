"""Terms, FAQ & Help and support ticket route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_CONTENT, SEGMENT_SUPPORT

CONTENT_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_CONTENT}"
SUPPORT_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_SUPPORT}"
OPENAPI_TAG_CONTENT: Final[str] = "content"
OPENAPI_TAG_SUPPORT: Final[str] = "support"

PATH_TERMS: Final[str] = "/terms"
PATH_FAQS: Final[str] = "/faqs"
PATH_TICKETS: Final[str] = "/tickets"

SLUG_TERMS: Final[str] = "terms"
AUDIENCE_ALL: Final[str] = "all"
FAQ_SEARCH_MAX_LENGTH: Final[int] = 100

MSG_CONTENT_NOT_FOUND: Final[str] = "Content not found."
MSG_SUPPORT_SHIFT_NOT_FOUND: Final[str] = "Shift not found."
