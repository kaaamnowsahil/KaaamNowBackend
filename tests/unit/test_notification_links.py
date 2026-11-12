"""Click targets stored on notification rows."""

from app.constants.notifications.notification_route_strings import (
    KIND_APPLICATION_SELECTED,
    KIND_EARNING_CREDITED,
    KIND_LIVE_REQUEST,
    KIND_NEW_MESSAGE,
    KIND_PAYMENT_RECEIVED,
    KIND_SHIFT_ENDED,
    KIND_VERIFICATION_UPDATED,
    KIND_WITHDRAWAL_PAID,
)
from app.services.notifications.notification_links import notification_path
from app.services.notifications.notification_service import _payload


def test_worker_and_business_pages() -> None:
    assert notification_path(KIND_LIVE_REQUEST, {"shift_id": "s1"}) == "/worker/shift/s1"
    assert (
        notification_path(
            KIND_LIVE_REQUEST, {"shift_id": "s1", "live_offer": "live_work"}, "worker"
        )
        == "/worker/live-work"
    )
    assert (
        notification_path(KIND_LIVE_REQUEST, {"shift_id": "s1", "live_work": True})
        == "/business/live-work/s1"
    )
    assert notification_path(KIND_APPLICATION_SELECTED, {"shift_id": "s1"}) == "/worker/shift/s1"
    assert notification_path(KIND_EARNING_CREDITED, {"invoice_id": "i1"}) == "/worker/earnings"
    assert notification_path(KIND_WITHDRAWAL_PAID, {"withdrawal_id": "w1"}) == (
        "/worker/earnings-history"
    )
    assert (
        notification_path(KIND_PAYMENT_RECEIVED, {"payment_id": "p1", "invoice_id": "i1"})
        == "/business/payments/detail?invoice=i1&payment=p1"
    )
    assert (
        notification_path(KIND_VERIFICATION_UPDATED, {"profile": "business"}) == "/business/profile"
    )
    assert notification_path(KIND_VERIFICATION_UPDATED, {"profile": "worker"}) == "/worker/profile"


def test_ambiguous_kinds_need_an_audience() -> None:
    data = {"shift_id": "s1", "assignment_id": "a1", "live_work": True}
    assert notification_path(KIND_SHIFT_ENDED, data) == "/notifications"
    assert notification_path(KIND_SHIFT_ENDED, data, "worker") == "/worker/live-work/a1"
    assert notification_path(KIND_SHIFT_ENDED, data, "business") == "/business/live-work/s1"
    assert notification_path(KIND_NEW_MESSAGE, data, "business") == "/business/live-work/s1"
    assert (
        notification_path(KIND_NEW_MESSAGE, {"shift_id": "s1", "assignment_id": "a1"}, "business")
        == "/business/booking/a1"
    )
    assert notification_path(KIND_NEW_MESSAGE, {"assignment_id": "a1"}, "worker") == (
        "/worker/booking/a1"
    )


def test_payload_stores_the_path() -> None:
    body = _payload(KIND_EARNING_CREDITED, {"invoice_id": "i1"}, None)
    assert body["path"] == "/worker/earnings"
    assert body["kind"] == KIND_EARNING_CREDITED
