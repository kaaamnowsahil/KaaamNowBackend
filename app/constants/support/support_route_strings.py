"""Admin booking overrides (rules §10) and the per-booking ledger view (§11)."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ADMIN

ADMIN_SUPPORT_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ADMIN}"
OPENAPI_TAG_ADMIN_SUPPORT: Final[str] = "admin - support"

PATH_BOOKING_LEDGER: Final[str] = "/bookings/{assignment_id}/ledger"
PATH_BOOKING_OVERRIDES: Final[str] = "/bookings/{assignment_id}/overrides"

ACTION_WAIVE_WORKER_FEE: Final[str] = "waive_worker_fee"
ACTION_VOID_STRIKE: Final[str] = "void_strike"
ACTION_UNBAN_WORKER: Final[str] = "unban_worker"
ACTION_REVOKE_VOUCHER: Final[str] = "revoke_voucher"
ACTION_REFUND_BUSINESS: Final[str] = "refund_business"
ENTRY_FEE_WAIVER: Final[str] = "fee_waiver"
WAIVABLE_ENTRY_TYPES: Final[tuple[str, ...]] = ("cancellation_fee", "adjustment")

MSG_BOOKING_NOT_FOUND: Final[str] = "Booking not found."
MSG_NOTHING_TO_WAIVE: Final[str] = "This booking has no worker fee left to waive."
MSG_NO_STRIKE: Final[str] = "This booking has no active strike."
MSG_NO_VOUCHER: Final[str] = "This booking has no active voucher."
MSG_REFUND_AMOUNT: Final[str] = "Refund needs an amount within what the business paid."
MSG_WORKER_NOT_RESTRICTED: Final[str] = "This worker isn't banned or limited."

PATH_SUPPORT_TICKET_STATUS: Final[str] = "/support-tickets/{ticket_id}/status"
SUPPORT_TICKET_RESOURCE: Final[str] = "support_tickets"
TICKET_STATUS_OPEN: Final[str] = "open"
TICKET_STATUS_IN_PROGRESS: Final[str] = "in_progress"
TICKET_STATUS_CLOSED: Final[str] = "closed"
MSG_TICKET_NOT_FOUND: Final[str] = "Support ticket not found."
MSG_TICKET_ALREADY_CLOSED: Final[str] = "This support ticket is already closed."
