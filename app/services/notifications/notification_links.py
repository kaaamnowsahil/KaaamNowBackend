"""Where a notification click should open. Stored on the row as ``data.path``."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from app.constants.notifications.notification_route_strings import (
    KIND_APPLICATION_CONFIRMED,
    KIND_APPLICATION_DECLINED,
    KIND_APPLICATION_RECEIVED,
    KIND_APPLICATION_REJECTED,
    KIND_APPLICATION_SELECTED,
    KIND_ATTENDANCE_APPROVED,
    KIND_BOOKING_ADJUSTED,
    KIND_CANCELLATION_COMPENSATION,
    KIND_CANCELLATION_FEE,
    KIND_EARNING_CREDITED,
    KIND_EXTENSION_PROMPT,
    KIND_EXTENSION_REQUESTED,
    KIND_INVOICE_READY,
    KIND_LIVE_ACCEPTED,
    KIND_LIVE_EXPIRED,
    KIND_LIVE_FILLED,
    KIND_LIVE_REQUEST,
    KIND_NO_SHOW,
    KIND_PAYMENT_RECEIVED,
    KIND_SEATS_RELEASED,
    KIND_SELECTION_EXPIRED,
    KIND_SHIFT_NEARBY,
    KIND_SHIFT_REMINDER,
    KIND_STRIKE_ADDED,
    KIND_VERIFICATION_UPDATED,
    KIND_VOUCHER_ISSUED,
    KIND_WITHDRAWAL_FAILED,
    KIND_WITHDRAWAL_PAID,
    KIND_WORKER_CHECKED_IN,
    KIND_WORKER_CHECKED_OUT,
    KIND_WORKER_EN_ROUTE,
)

INBOX = "/notifications"
_WORKER = "worker"
_BUSINESS = "business"

_WORKER_KINDS = frozenset(
    {
        KIND_SHIFT_NEARBY,
        KIND_APPLICATION_SELECTED,
        KIND_APPLICATION_REJECTED,
        KIND_EARNING_CREDITED,
        KIND_WITHDRAWAL_PAID,
        KIND_WITHDRAWAL_FAILED,
        KIND_STRIKE_ADDED,
        KIND_CANCELLATION_FEE,
        KIND_CANCELLATION_COMPENSATION,
        KIND_NO_SHOW,
        KIND_ATTENDANCE_APPROVED,
        KIND_EXTENSION_REQUESTED,
        KIND_SHIFT_REMINDER,
    }
)
_BUSINESS_KINDS = frozenset(
    {
        KIND_PAYMENT_RECEIVED,
        KIND_APPLICATION_CONFIRMED,
        KIND_APPLICATION_DECLINED,
        KIND_APPLICATION_RECEIVED,
        KIND_VOUCHER_ISSUED,
        KIND_SEATS_RELEASED,
        KIND_EXTENSION_PROMPT,
        KIND_LIVE_ACCEPTED,
        KIND_LIVE_FILLED,
        KIND_LIVE_EXPIRED,
        KIND_WORKER_EN_ROUTE,
        KIND_WORKER_CHECKED_IN,
        KIND_WORKER_CHECKED_OUT,
        KIND_INVOICE_READY,
    }
)


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return "" if value is None else str(value)


def _flag(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _audience(kind: str, data: dict[str, Any], audience: str | None) -> str | None:
    if audience in (_WORKER, _BUSINESS):
        return audience
    if kind == KIND_LIVE_REQUEST:
        # Business "finding Workers" sets live_work. Worker offers pass audience explicitly.
        return _BUSINESS if _flag(data, "live_work") else _WORKER
    if kind == KIND_VERIFICATION_UPDATED:
        return _BUSINESS if data.get("profile") == "business" else _WORKER
    if kind in _WORKER_KINDS:
        return _WORKER
    if kind in _BUSINESS_KINDS:
        return _BUSINESS
    return None


def _payment_path(data: dict[str, Any]) -> str:
    query = {key: _text(data, key) for key in ("invoice_id", "payment_id") if _text(data, key)}
    renamed = {}
    if query.get("invoice_id"):
        renamed["invoice"] = query["invoice_id"]
    if query.get("payment_id"):
        renamed["payment"] = query["payment_id"]
    if not renamed:
        return "/business/payments"
    return f"/business/payments/detail?{urlencode(renamed)}"


def _worker_path(kind: str, data: dict[str, Any], shift_id: str, assignment_id: str) -> str:
    live = _flag(data, "live_work")
    if kind == KIND_LIVE_REQUEST:
        return f"/worker/shift/{shift_id}" if shift_id else "/worker/live-work"
    if kind == KIND_EARNING_CREDITED:
        return "/worker/earnings"
    if kind in (KIND_WITHDRAWAL_PAID, KIND_WITHDRAWAL_FAILED):
        return "/worker/earnings-history"
    if kind == KIND_VERIFICATION_UPDATED:
        return "/worker/profile"
    if kind == KIND_STRIKE_ADDED and not assignment_id:
        return "/worker/profile"
    if kind == KIND_BOOKING_ADJUSTED and not assignment_id and not shift_id:
        return "/worker/profile"
    if kind in (KIND_APPLICATION_REJECTED, KIND_SELECTION_EXPIRED) and not assignment_id:
        if shift_id and kind == KIND_APPLICATION_REJECTED:
            return f"/worker/shift/{shift_id}"
        return "/worker/shifts"
    if kind in (KIND_SHIFT_NEARBY, KIND_APPLICATION_SELECTED, KIND_SHIFT_REMINDER) and shift_id:
        return f"/worker/shift/{shift_id}"
    if live and assignment_id:
        return f"/worker/live-work/{assignment_id}"
    if assignment_id:
        return f"/worker/booking/{assignment_id}"
    if shift_id:
        return f"/worker/shift/{shift_id}"
    return "/worker/shifts"


def _business_path(kind: str, data: dict[str, Any], shift_id: str, assignment_id: str) -> str:
    live = _flag(data, "live_work")
    if kind in (KIND_PAYMENT_RECEIVED, KIND_INVOICE_READY):
        return _payment_path(data)
    if kind == KIND_BOOKING_ADJUSTED and _text(data, "invoice_id"):
        return _payment_path(data)
    if kind == KIND_VERIFICATION_UPDATED:
        return "/business/profile"
    if kind in (KIND_APPLICATION_DECLINED, KIND_APPLICATION_RECEIVED, KIND_SELECTION_EXPIRED):
        return "/business/applicants"
    if kind == KIND_VOUCHER_ISSUED:
        return "/business/shifts"
    if live and shift_id:
        return f"/business/live-work/{shift_id}"
    if kind in (KIND_LIVE_ACCEPTED, KIND_LIVE_FILLED, KIND_LIVE_EXPIRED, KIND_LIVE_REQUEST):
        return "/business/live"
    if assignment_id:
        return f"/business/booking/{assignment_id}"
    if shift_id:
        return "/business/shifts"
    return "/business/live"


def notification_path(kind: str, data: dict[str, Any] | None, audience: str | None = None) -> str:
    """App path for this notification. ``/notifications`` when nothing more specific is known."""
    payload = data or {}
    who = _audience(kind, payload, audience)
    if who is None:
        return INBOX
    shift_id = _text(payload, "shift_id")
    assignment_id = _text(payload, "assignment_id")
    if who == _WORKER:
        return _worker_path(kind, payload, shift_id, assignment_id)
    return _business_path(kind, payload, shift_id, assignment_id)
