"""Admin account-deletion review routes and messages."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ADMIN

ADMIN_DELETION_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ADMIN}"
PATH_DELETION_REQUESTS: Final[str] = "/account-deletion-requests"
PATH_DELETION_REQUEST: Final[str] = "/account-deletion-requests/{request_id}"
PATH_DELETION_APPROVE: Final[str] = "/account-deletion-requests/{request_id}/approve"
PATH_DELETION_HOLDS: Final[str] = "/account-deletion-requests/{request_id}/holds"
PATH_DELETION_HOLD: Final[str] = "/account-deletion-requests/{request_id}/holds/{hold_id}"

MSG_DELETION_HOLD_EXPIRES: Final[str] = "A review hold must expire within 30 days."
MSG_DELETION_HOLD_REASON: Final[str] = (
    "A documented reason and case reference are required for this hold."
)
MSG_DELETION_APPROVAL_BLOCKED: Final[str] = (
    "This request cannot be approved while active retention blockers remain."
)
