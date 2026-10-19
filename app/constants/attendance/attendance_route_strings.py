"""Check-in / check-out / attendance review route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_BUSINESS, SEGMENT_WORKER

WORKER_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKER}"
BUSINESS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_BUSINESS}"
OPENAPI_TAG_ATTENDANCE: Final[str] = "attendance"

PATH_CHECK_IN: Final[str] = "/assignments/{assignment_id}/check-in"
PATH_CHECK_OUT: Final[str] = "/assignments/{assignment_id}/check-out"
PATH_APPROVE: Final[str] = "/assignments/{assignment_id}/attendance/approve"
PATH_NO_SHOW: Final[str] = "/assignments/{assignment_id}/no-show"

MSG_CHECK_IN_NOT_OPEN: Final[str] = "Check-in opens 30 minutes before the shift starts."
MSG_CHECK_IN_CLOSED: Final[str] = "This shift has already ended."
MSG_CHECK_IN_TOO_FAR: Final[str] = "You need to be at the workplace to check in."
MSG_CHECK_IN_CODE: Final[str] = "That check-in code is not correct. Ask the site contact."
MSG_NOT_CHECKED_IN: Final[str] = "You are not checked in to this shift."
MSG_NOT_CHECKED_OUT: Final[str] = "The worker has not checked out yet."
MSG_NO_SHOW_TOO_EARLY: Final[str] = "You can mark a no-show 30 minutes after the shift starts."
MSG_APPROVED_MINUTES_TOO_HIGH: Final[str] = "Approved time cannot exceed the scheduled shift."
