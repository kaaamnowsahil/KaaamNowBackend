"""Notification route constants and the notification kinds the app renders."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_NOTIFICATIONS

NOTIFICATIONS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_NOTIFICATIONS}"
OPENAPI_TAG_NOTIFICATIONS: Final[str] = "notifications"

PATH_UNREAD_COUNT: Final[str] = "/unread-count"
PATH_READ_ONE: Final[str] = "/{notification_id}/read"
PATH_READ_ALL: Final[str] = "/read-all"

KIND_LIVE_REQUEST: Final[str] = "live_request"
KIND_LIVE_ACCEPTED: Final[str] = "live_worker_accepted"
KIND_LIVE_FILLED: Final[str] = "live_shift_filled"
KIND_LIVE_EXPIRED: Final[str] = "live_search_expired"
KIND_SHIFT_NEARBY: Final[str] = "scheduled_shift_nearby"
KIND_APPLICATION_RECEIVED: Final[str] = "application_received"
KIND_APPLICATION_SELECTED: Final[str] = "application_selected"
KIND_APPLICATION_REJECTED: Final[str] = "application_rejected"
KIND_APPLICATION_CONFIRMED: Final[str] = "application_confirmed"
KIND_APPLICATION_DECLINED: Final[str] = "application_declined"
KIND_SELECTION_EXPIRED: Final[str] = "selection_expired"
KIND_SHIFT_CANCELLED: Final[str] = "shift_cancelled"
KIND_ASSIGNMENT_CANCELLED: Final[str] = "assignment_cancelled"
KIND_WORKER_EN_ROUTE: Final[str] = "worker_en_route"
KIND_WORKER_CHECKED_IN: Final[str] = "worker_checked_in"
KIND_WORKER_CHECKED_OUT: Final[str] = "worker_checked_out"
KIND_ATTENDANCE_APPROVED: Final[str] = "attendance_approved"
KIND_NO_SHOW: Final[str] = "no_show"
KIND_INVOICE_READY: Final[str] = "invoice_ready"
KIND_PAYMENT_RECEIVED: Final[str] = "payment_received"
KIND_EARNING_CREDITED: Final[str] = "earning_credited"
KIND_WITHDRAWAL_PAID: Final[str] = "withdrawal_paid"
KIND_WITHDRAWAL_FAILED: Final[str] = "withdrawal_failed"
KIND_NEW_MESSAGE: Final[str] = "new_message"
KIND_RATING_RECEIVED: Final[str] = "rating_received"
KIND_VERIFICATION_UPDATED: Final[str] = "verification_updated"
KIND_SHIFT_REMINDER: Final[str] = "shift_reminder"

PUSH_BATCH_SIZE: Final[int] = 200
# A push still failing transiently after this many sweeps is marked ``failed``.
PUSH_MAX_ATTEMPTS: Final[int] = 3

MSG_NOTIFICATION_NOT_FOUND: Final[str] = "Notification not found."
KIND_CANCELLATION_FEE: Final[str] = "cancellation_fee"
KIND_CANCELLATION_COMPENSATION: Final[str] = "cancellation_compensation"
KIND_STRIKE_ADDED: Final[str] = "strike_added"
KIND_VOUCHER_ISSUED: Final[str] = "voucher_issued"
KIND_SEATS_RELEASED: Final[str] = "seats_released"
KIND_SHIFT_ENDED: Final[str] = "shift_ended"
KIND_EARLY_END_REQUESTED: Final[str] = "early_end_requested"
KIND_EXTENSION_REQUESTED: Final[str] = "extension_requested"
KIND_EXTENSION_ANSWERED: Final[str] = "extension_answered"
KIND_EXTENSION_PROMPT: Final[str] = "extension_prompt"
KIND_SUPPORT_EMERGENCY: Final[str] = "support_emergency"
KIND_BOOKING_ADJUSTED: Final[str] = "booking_adjusted"
