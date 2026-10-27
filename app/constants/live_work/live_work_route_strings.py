"""Live Work (Business / Work, Worker, Admin) route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import (
    API_V1,
    SEGMENT_ADMIN,
    SEGMENT_BUSINESS,
    SEGMENT_WORKER,
)

BUSINESS_LIVE_WORK_PREFIX: Final[str] = f"{API_V1}{SEGMENT_BUSINESS}/live-work"
WORKER_LIVE_WORK_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKER}/live-work"
ADMIN_LIVE_WORK_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ADMIN}/live-work"

OPENAPI_TAG_BUSINESS_LIVE_WORK: Final[str] = "Business / Work — Live Work"
OPENAPI_TAG_WORKER_LIVE_WORK: Final[str] = "Worker — Live Work"
OPENAPI_TAG_ADMIN_LIVE_WORK: Final[str] = "Admin — Live Work"

# Business / Work
PATH_QUOTE: Final[str] = "/quote"
PATH_AVAILABLE_WORKERS: Final[str] = "/available-workers"
PATH_BOOKINGS: Final[str] = ""
PATH_BOOKING: Final[str] = "/{booking_id}"
PATH_BOOKING_CANCEL_PREVIEW: Final[str] = "/{booking_id}/cancel-preview"
PATH_BOOKING_CANCEL: Final[str] = "/{booking_id}/cancel"
PATH_BOOKING_EXTENSION_QUOTE: Final[str] = "/{booking_id}/extension-quote"
PATH_BOOKING_EXTENSIONS: Final[str] = "/{booking_id}/extensions"
PATH_BOOKING_EXTENSION_CANCEL: Final[str] = "/{booking_id}/extensions/{extension_id}/cancel"
PATH_BOOKING_END: Final[str] = "/{booking_id}/end"
PATH_BOOKING_ARRIVAL_CODE: Final[str] = "/{booking_id}/arrival-code/reissue"

# Worker
PATH_REQUESTS: Final[str] = "/requests"
PATH_REQUEST_ACCEPT: Final[str] = "/requests/{booking_id}/accept"
PATH_REQUEST_DECLINE: Final[str] = "/requests/{booking_id}/decline"
PATH_ACTIVE: Final[str] = "/active"
PATH_WORKER_BOOKINGS: Final[str] = "/bookings"
PATH_WORKER_BOOKING: Final[str] = "/bookings/{assignment_id}"
PATH_WORKER_START_TRAVEL: Final[str] = "/bookings/{assignment_id}/start-travel"
PATH_WORKER_LOCATION: Final[str] = "/bookings/{assignment_id}/location"
PATH_WORKER_START: Final[str] = "/bookings/{assignment_id}/start"
PATH_WORKER_COMPLETE: Final[str] = "/bookings/{assignment_id}/complete"
PATH_WORKER_CANCEL_PREVIEW: Final[str] = "/bookings/{assignment_id}/cancel-preview"
PATH_WORKER_CANCEL: Final[str] = "/bookings/{assignment_id}/cancel"
PATH_WORKER_EXTENSION_ANSWER: Final[str] = "/bookings/{assignment_id}/extensions/{extension_id}"

# Admin
PATH_ADMIN_PRICING: Final[str] = "/pricing"
PATH_ADMIN_PRICING_AUDIT: Final[str] = "/pricing/audit"
PATH_ADMIN_BOOKINGS: Final[str] = "/bookings"
PATH_ADMIN_BOOKING: Final[str] = "/bookings/{booking_id}"
PATH_ADMIN_REFUNDS: Final[str] = "/refunds"
PATH_ADMIN_REFUND_RETRY: Final[str] = "/refunds/{refund_id}/retry"
