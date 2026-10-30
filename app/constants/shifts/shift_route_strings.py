"""Shift, live dispatch, application and assignment route + status constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import (
    API_V1,
    SEGMENT_ASSIGNMENTS,
    SEGMENT_BUSINESS,
    SEGMENT_WORKER,
)

BUSINESS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_BUSINESS}"
WORKER_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKER}"
ASSIGNMENTS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ASSIGNMENTS}"

OPENAPI_TAG_BUSINESS_SHIFTS: Final[str] = "business / work shifts"
OPENAPI_TAG_BUSINESS_LIVE: Final[str] = "business / work live"
OPENAPI_TAG_WORKER_SHIFTS: Final[str] = "worker shifts"
OPENAPI_TAG_WORKER_LIVE: Final[str] = "worker live"
OPENAPI_TAG_ASSIGNMENTS: Final[str] = "assignments"

# --- Business paths ---
PATH_DASHBOARD: Final[str] = "/dashboard"
PATH_SHIFTS: Final[str] = "/shifts"
PATH_SHIFT: Final[str] = "/shifts/{shift_id}"
PATH_SHIFT_ESTIMATE: Final[str] = "/shifts/estimate"
PATH_SHIFTS_BULK: Final[str] = "/shifts/bulk"
PATH_SHIFTS_BULK_PUBLISH: Final[str] = "/shifts/bulk-publish"
MAX_BULK_SHIFTS: Final[int] = 31
PATH_SHIFT_PUBLISH: Final[str] = "/shifts/{shift_id}/publish"
PATH_SHIFT_CANCEL: Final[str] = "/shifts/{shift_id}/cancel"
PATH_SHIFT_CANCEL_PREVIEW: Final[str] = "/shifts/{shift_id}/cancel-preview"
PATH_SHIFT_CONVERT: Final[str] = "/shifts/{shift_id}/convert-to-scheduled"
PATH_SHIFT_RETRY_LIVE: Final[str] = "/shifts/{shift_id}/retry-live"
PATH_SHIFT_LIVE_SEARCH: Final[str] = "/shifts/{shift_id}/live-search"
PATH_SHIFT_ROSTER: Final[str] = "/shifts/{shift_id}/roster"
PATH_SHIFT_APPLICATIONS: Final[str] = "/shifts/{shift_id}/applications"
PATH_BUSINESS_APPLICATIONS: Final[str] = "/applications"
PATH_APPLICATION_SELECT: Final[str] = "/applications/{application_id}/select"
PATH_APPLICATION_REJECT: Final[str] = "/applications/{application_id}/reject"
PATH_BUSINESS_ASSIGNMENT_CANCEL: Final[str] = "/assignments/{assignment_id}/cancel"
PATH_BUSINESS_ASSIGNMENT_CANCEL_PREVIEW: Final[str] = "/assignments/{assignment_id}/cancel-preview"

# --- Worker paths ---
PATH_FEED: Final[str] = "/feed"
PATH_WORKER_SHIFT: Final[str] = "/shifts/{shift_id}"
PATH_MY_SHIFTS: Final[str] = "/my-shifts"
PATH_LIVE_REQUESTS: Final[str] = "/live-requests"
PATH_LIVE_ACCEPT: Final[str] = "/live-shifts/{shift_id}/accept"
PATH_LIVE_DECLINE: Final[str] = "/live-shifts/{shift_id}/decline"
PATH_APPLY: Final[str] = "/shifts/{shift_id}/applications"
PATH_APPLICATION_WITHDRAW: Final[str] = "/applications/{application_id}/withdraw"
PATH_APPLICATION_CONFIRM: Final[str] = "/applications/{application_id}/confirm"
PATH_APPLICATION_DECLINE: Final[str] = "/applications/{application_id}/decline"
PATH_START_TRAVEL: Final[str] = "/assignments/{assignment_id}/start-travel"
PATH_WORKER_ASSIGNMENT_CANCEL: Final[str] = "/assignments/{assignment_id}/cancel"
PATH_WORKER_ASSIGNMENT_CANCEL_PREVIEW: Final[str] = "/assignments/{assignment_id}/cancel-preview"

# --- Shared assignment paths ---
PATH_ASSIGNMENT: Final[str] = "/{assignment_id}"
PATH_ASSIGNMENT_TRACKING: Final[str] = "/{assignment_id}/tracking"
PATH_ASSIGNMENT_CONTACT: Final[str] = "/{assignment_id}/contact"
PATH_ASSIGNMENT_MESSAGES: Final[str] = "/{assignment_id}/messages"

# --- Shift types / statuses ---
SHIFT_LIVE: Final[str] = "live"
SHIFT_SCHEDULED: Final[str] = "scheduled"

SHIFT_DRAFT: Final[str] = "draft"
SHIFT_AWAITING_PAYMENT: Final[str] = "awaiting_payment"
SHIFT_SEARCHING: Final[str] = "searching"
SHIFT_OPEN: Final[str] = "open"
SHIFT_FILLED: Final[str] = "filled"
SHIFT_IN_PROGRESS: Final[str] = "in_progress"
SHIFT_COMPLETED: Final[str] = "completed"
SHIFT_EXPIRED: Final[str] = "expired"
SHIFT_CANCELLED: Final[str] = "cancelled"

SHIFT_RECRUITING_STATUSES: Final[tuple[str, ...]] = (SHIFT_SEARCHING, SHIFT_OPEN)

DASHBOARD_GROUP_COMPLETED: Final[str] = "completed"
DASHBOARD_GROUP_UPCOMING: Final[str] = "upcoming"
DASHBOARD_GROUP_IN_PROGRESS: Final[str] = "in_progress"
DASHBOARD_GROUP_EXPIRED: Final[str] = "expired"
# Business Shifts page sections, in display order.
SHIFT_GROUPS: Final[tuple[tuple[str, str], ...]] = (
    ("upcoming", "Coming up"),
    ("in_progress", "In progress"),
    ("draft", "Drafts"),
    ("completed", "Completed"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
)
DASHBOARD_NEXT_SCHEDULED_LIMIT: Final[int] = 2
DASHBOARD_UPCOMING_STATUSES: Final[tuple[str, ...]] = (
    SHIFT_AWAITING_PAYMENT,
    SHIFT_SEARCHING,
    SHIFT_OPEN,
    SHIFT_FILLED,
)
# Section order and titles on Business / Work Home.
DASHBOARD_GROUPS: Final[tuple[tuple[str, str], ...]] = (
    (DASHBOARD_GROUP_COMPLETED, "Completed"),
    (DASHBOARD_GROUP_UPCOMING, "Coming up"),
    (DASHBOARD_GROUP_IN_PROGRESS, "In progress"),
    (DASHBOARD_GROUP_EXPIRED, "Expired"),
)
SHIFT_CANCELLABLE_STATUSES: Final[tuple[str, ...]] = (
    SHIFT_DRAFT,
    SHIFT_AWAITING_PAYMENT,
    SHIFT_SEARCHING,
    SHIFT_OPEN,
    SHIFT_FILLED,
)

DISPATCH_OFFERED: Final[str] = "offered"
DISPATCH_ACCEPTED: Final[str] = "accepted"
DISPATCH_DECLINED: Final[str] = "declined"
DISPATCH_EXPIRED: Final[str] = "expired"
DISPATCH_WITHDRAWN: Final[str] = "withdrawn"

APP_APPLIED: Final[str] = "applied"
APP_SELECTED: Final[str] = "selected"
APP_CONFIRMED: Final[str] = "confirmed"
APP_DECLINED: Final[str] = "declined"
APP_REJECTED: Final[str] = "rejected"
APP_WITHDRAWN: Final[str] = "withdrawn"
APP_EXPIRED: Final[str] = "expired"

ASG_CONFIRMED: Final[str] = "confirmed"
ASG_EN_ROUTE: Final[str] = "en_route"
ASG_CHECKED_IN: Final[str] = "checked_in"
ASG_CHECKED_OUT: Final[str] = "checked_out"
ASG_APPROVED: Final[str] = "approved"
ASG_NO_SHOW: Final[str] = "no_show"
ASG_CANCELLED: Final[str] = "cancelled"

ASG_BOOKED_STATUSES: Final[tuple[str, ...]] = (ASG_CONFIRMED, ASG_EN_ROUTE)
ASG_SEAT_HOLDING_STATUSES: Final[tuple[str, ...]] = (
    ASG_CONFIRMED,
    ASG_EN_ROUTE,
    ASG_CHECKED_IN,
    ASG_CHECKED_OUT,
    ASG_APPROVED,
)
ASG_WORKED_STATUSES: Final[tuple[str, ...]] = (ASG_CHECKED_OUT, ASG_APPROVED)

EXTENSION_REQUESTED: Final[str] = "requested"
EXTENSION_ACCEPTED: Final[str] = "accepted"
EXTENSION_DECLINED: Final[str] = "declined"
END_SCHEDULED: Final[str] = "scheduled_end"
END_MUTUAL: Final[str] = "mutual"
END_BUSINESS_STOPPED: Final[str] = "business_stopped"
END_WORKER_LEFT: Final[str] = "worker_left"
END_COMPLETED: Final[str] = "completed"

PRICING_HOURLY: Final[str] = "hourly"
PRICING_TASK: Final[str] = "task"

MY_SHIFTS_TABS: Final[tuple[str, ...]] = ("upcoming", "active", "completed", "applications")
DASHBOARD_TABS: Final[tuple[str, ...]] = ("live", "scheduled")
FEED_SORTS: Final[tuple[str, ...]] = ("distance", "starts_at", "pay")

CHECK_IN_CODE_LENGTH: Final[int] = 4
MIN_SHIFT_MINUTES: Final[int] = 60
MAX_SHIFT_HOURS: Final[int] = 16
MAX_SCHEDULE_AHEAD_DAYS: Final[int] = 60
LIVE_START_TOLERANCE_MINUTES: Final[int] = 30
TRAVEL_OPENS_HOURS_BEFORE: Final[int] = 3
MESSAGES_PAGE_LIMIT: Final[int] = 200
SCHEDULED_NOTIFY_BATCH_SIZE: Final[int] = 500

# --- Messages ---
MSG_SHIFT_NOT_FOUND: Final[str] = "Shift not found."
MSG_SHIFT_NOT_DRAFT: Final[str] = "Only draft shifts can be edited or published."
MSG_SHIFT_NOT_CANCELLABLE: Final[str] = "This shift can no longer be cancelled."
MSG_SHIFT_CANCELLATION_CUTOFF: Final[str] = (
    "This shift can only be cancelled at least {hours} hours before it starts."
)
MSG_WORKER_CANCELLATION_CUTOFF: Final[str] = (
    "You can only withdraw at least {hours} hours before the shift starts."
)
MSG_CANCEL_REASON_REQUIRED: Final[str] = "Tell the business why you're withdrawing."
MSG_SHIFT_NOT_RECRUITING: Final[str] = "This shift is no longer accepting workers."
MSG_SHIFT_FULL: Final[str] = "All spots for this shift are filled."
MSG_SHIFT_STARTED: Final[str] = "This shift has already started."
MSG_SHIFT_WINDOW_INVALID: Final[str] = "The shift must end after it starts."
MSG_SHIFT_TOO_SHORT: Final[str] = "Shifts must be at least 1 hour long."
MSG_SHIFT_TOO_LONG: Final[str] = "Shifts can be at most 16 hours long."
MSG_SHIFT_IN_PAST: Final[str] = "Scheduled shifts must start in the future."
MSG_SHIFT_TOO_FAR: Final[str] = "Shifts can be scheduled at most 60 days ahead."
MSG_SHIFT_TOO_SOON: Final[str] = "Shifts must be posted at least {hours} hours before they start."
MSG_APPLY_CLOSED: Final[str] = "Booking for this shift closed {hours} hours before it starts."
MSG_TOO_MANY_BOOKINGS: Final[str] = (
    "You already have {count} upcoming shifts. Finish or cancel one to book another."
)
MSG_LIVE_START_NOW: Final[str] = "Live shifts must start now (within 30 minutes)."
MSG_BREAK_TOO_LONG: Final[str] = "Break is longer than the shift."
MSG_CONVERT_NOT_ALLOWED: Final[str] = (
    "Only a live search with no accepted workers can be converted to scheduled."
)
MSG_RETRY_NOT_ALLOWED: Final[str] = "Only an expired live search can be retried."
MSG_NOT_LIVE_SHIFT: Final[str] = "This action is only for live shifts."
MSG_NOT_SCHEDULED_SHIFT: Final[str] = "This action is only for scheduled shifts."
MSG_NO_LIVE_OFFER: Final[str] = "This request is no longer available to you."
MSG_ALREADY_BOOKED: Final[str] = "You are already booked on this shift."
MSG_OVERLAPPING_SHIFT: Final[str] = "You already have a shift at this time."
MSG_WORKER_UNAVAILABLE: Final[str] = "This worker is already booked for another shift at this time."
MSG_TOO_FAR_FROM_SHIFT: Final[str] = "You are outside this shift's search radius."
MSG_SHIFT_BEYOND_MAX_DISTANCE: Final[str] = (
    "You're too far from this shift (more than {km:g} km). Try finding shifts nearby."
)
MSG_SHIFT_LOCATION_REQUIRED: Final[str] = "Pick the shift address on the map before saving."
MSG_LOCATION_STALE: Final[str] = "Your location is out of date. Go online again."
MSG_APPLICATION_NOT_FOUND: Final[str] = "Application not found."
MSG_APPLICATION_EXISTS: Final[str] = "You have already applied to this shift."
MSG_APPLICATION_STATE: Final[str] = "This application can no longer be changed."
MSG_CONFIRM_EXPIRED: Final[str] = "The time to confirm this selection has passed."
MSG_ASSIGNMENT_NOT_FOUND: Final[str] = "Booking not found."
MSG_ASSIGNMENT_STATE: Final[str] = "This booking can no longer be changed."
MSG_TRAVEL_TOO_EARLY: Final[str] = "You can start travelling closer to the shift start."
MSG_TRACKING_UNAVAILABLE: Final[str] = "Live location is not available for this worker."
