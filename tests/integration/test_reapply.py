"""Apply / accept again after the worker withdrew or cancelled: once per shift, never after
the business removed them."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from tests.integration.conftest import Actor
from tests.integration.test_cancellations import _booked_shift
from tests.integration.test_live_work import BIZ, WRK, _accepted, _location, _place_worker

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"


async def _detail(client: httpx.AsyncClient, worker: Actor, shift_id: str) -> dict:
    resp = await client.get(f"{API}/worker/shifts/{shift_id}", headers=worker.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _my_assignment(client: httpx.AsyncClient, worker: Actor, shift_id: str) -> str:
    my = (await client.get(f"{API}/worker/my-shifts", headers=worker.headers)).json()
    return next(i["assignment_id"] for i in my["items"] if i["shift"]["id"] == shift_id)


async def _worker_cancel(client: httpx.AsyncClient, worker: Actor, assignment_id: str) -> None:
    resp = await client.post(
        f"{API}/worker/assignments/{assignment_id}/cancel",
        json={"reason": "Plans changed"},
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text


async def test_scheduled_reapply_once_after_worker_cancel(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Comes Back", online=False)
    shift_id, (first,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(days=2)
    )
    assert (await _detail(app_client, worker, shift_id))["can_reapply"] is False

    await _worker_cancel(app_client, worker, first)
    detail = await _detail(app_client, worker, shift_id)
    assert detail["my_application_status"] == "withdrawn"
    assert detail["can_reapply"] is True
    assert detail["reapply_block_reason"] is None

    again = await app_client.post(
        f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
    )
    assert again.status_code == 201, again.text
    second = await _my_assignment(app_client, worker, shift_id)
    assert second != first

    await _worker_cancel(app_client, worker, second)
    detail = await _detail(app_client, worker, shift_id)
    assert detail["can_reapply"] is False
    assert detail["reapply_block_reason"] == "reapply_limit"
    refused = await app_client.post(
        f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "reapply_limit"


async def test_no_reapply_after_business_removes_worker(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Removed", online=False)
    shift_id, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(days=2), seats=2
    )
    removed = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/cancel",
        json={"reason": "Not needed"},
        headers=business.headers,
    )
    assert removed.status_code == 200, removed.text
    detail = await _detail(app_client, worker, shift_id)
    assert detail["can_reapply"] is False
    assert detail["reapply_block_reason"] == "business_cancelled"
    refused = await app_client.post(
        f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "application_exists"


async def test_live_reaccept_once_after_cancel_before_start(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Live Returner")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _accepted(app_client, business, worker, lat, lng)
    booking_id = booking["booking_id"]

    cancel = await app_client.post(
        f"{WRK}/bookings/{job['assignment_id']}/cancel", json={}, headers=worker.headers
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["actions"]["can_accept_again"] is True
    detail = await _detail(app_client, worker, booking_id)
    assert detail["can_reapply"] is True

    again = await app_client.post(f"{WRK}/requests/{booking_id}/accept", headers=worker.headers)
    assert again.status_code == 200, again.text
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["status"] == "assigned"

    cancel = await app_client.post(
        f"{WRK}/bookings/{again.json()['assignment_id']}/cancel", json={}, headers=worker.headers
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["actions"]["can_accept_again"] is False
    detail = await _detail(app_client, worker, booking_id)
    assert detail["can_reapply"] is False
    assert detail["reapply_block_reason"] == "reapply_limit"
    refused = await app_client.post(f"{WRK}/requests/{booking_id}/accept", headers=worker.headers)
    assert refused.status_code == 409
    assert refused.json()["code"] == "reapply_limit"
