"""Task (fixed-price) bookings for Shift and Live Work, and the completion code the worker needs
from the Business to finish. Task price ₹600 per seat; no early/late timing, no extensions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from app.services.background.background_sweep_loop import run_sweep_once
from tests.integration.conftest import completion_code, live_completion_code, pay_deposit
from tests.integration.test_live_work import (
    BIZ,
    WRK,
    _create_body,
    _location,
    _pay,
    _place_worker,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
NEAR = {"latitude": 28.6316, "longitude": 77.2168}
TASK = 60000
TASK_COMMISSION = 2400  # 4%
TASK_GATEWAY = 1248  # 2% of task + commission
TASK_TAX = 1248  # 2% of task + commission
TASK_SEAT_TOTAL = TASK + TASK_COMMISSION + TASK_GATEWAY + TASK_TAX


def _task_body(**overrides: object) -> dict:
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    body: dict = {
        "shift_type": "scheduled",
        "category_slug": "house-help",
        "job_title": "Deep clean the kitchen",
        "workers_required": 1,
        "pricing_mode": "task",
        "task_price_minor": TASK,
        "starts_at": starts.isoformat(),
        "publish": True,
    }
    body.update(overrides)
    return body


async def _booked_task(  # type: ignore[no-untyped-def]
    client: httpx.AsyncClient, db: asyncpg.Connection, business, worker
) -> tuple[str, str]:
    resp = await client.post(f"{API}/business/shifts", json=_task_body(), headers=business.headers)
    assert resp.status_code == 201, resp.text
    shift_id = resp.json()["id"]
    await pay_deposit(client, business, shift_id)
    applied = await client.post(
        f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
    )
    assert applied.status_code == 201, applied.text
    my = (await client.get(f"{API}/worker/my-shifts", headers=worker.headers)).json()
    item = next(i for i in my["items"] if i["shift"]["id"] == shift_id)
    assert item["shift"]["pricing_mode"] == "task"
    assert item["shift"]["task_price_minor"] == TASK
    start = datetime.now(UTC) - timedelta(minutes=10)
    await db.execute(
        "UPDATE shifts SET starts_at = $2, ends_at = $3 WHERE id = $1",
        UUID(shift_id),
        start,
        start + timedelta(hours=12),
    )
    detail = await client.get(
        f"{API}/assignments/{item['assignment_id']}", headers=business.headers
    )
    checked_in = await client.post(
        f"{API}/worker/assignments/{item['assignment_id']}/check-in",
        json={**NEAR, "check_in_code": detail.json()["check_in_code"]},
        headers=worker.headers,
    )
    assert checked_in.status_code == 200, checked_in.text
    return shift_id, item["assignment_id"]


async def _invoice(client: httpx.AsyncClient, business, shift_id: str) -> dict:  # type: ignore[no-untyped-def]
    resp = await client.post(f"{API}/business/shifts/{shift_id}/invoice", headers=business.headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _worker_pay(invoice: dict) -> int:
    return sum(
        line["amount_minor"] for line in invoice["lines"] if line["line_kind"] == "worker_pay"
    )


# --- scheduled shift ------------------------------------------------------------------


async def test_task_shift_pricing_validation_and_deposit(  # type: ignore[no-untyped-def]
    app_client, db, make_business
) -> None:
    business = await make_business()
    missing = await app_client.post(
        f"{API}/business/shifts",
        json=_task_body(task_price_minor=None),
        headers=business.headers,
    )
    assert missing.status_code == 422, missing.text
    no_rate = await app_client.post(
        f"{API}/business/shifts",
        json=_task_body(pricing_mode="hourly", task_price_minor=None, duration_minutes=240),
        headers=business.headers,
    )
    assert no_rate.status_code == 422, no_rate.text

    estimate = await app_client.post(
        f"{API}/business/shifts/estimate",
        json={"pricing_mode": "task", "task_price_minor": TASK, "workers_required": 2},
        headers=business.headers,
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["pricing_mode"] == "task"
    assert estimate.json()["task_price_minor"] == TASK

    created = await app_client.post(
        f"{API}/business/shifts", json=_task_body(), headers=business.headers
    )
    assert created.status_code == 201, created.text
    shift = created.json()
    assert shift["pricing_mode"] == "task"
    assert shift["task_price_minor"] == TASK
    assert shift["hourly_rate_minor"] == 0
    starts = datetime.fromisoformat(shift["starts_at"])
    ends = datetime.fromisoformat(shift["ends_at"])
    assert ends - starts == timedelta(hours=12)
    total = await db.fetchval(
        "SELECT total_minor FROM shift_invoices WHERE id = $1", UUID(shift["deposit_invoice_id"])
    )
    assert total == TASK_SEAT_TOTAL


async def test_task_shift_completion_code_lock_reissue_and_pay(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Task Worker", online=False)
    shift_id, assignment_id = await _booked_task(app_client, db, business, worker)

    for path, headers, body in (
        ("worker/assignments/{a}/early-end/request", worker.headers, None),
        ("business/assignments/{a}/extensions", business.headers, {"extra_minutes": 60}),
    ):
        blocked = await app_client.post(
            f"{API}/{path.format(a=assignment_id)}", json=body, headers=headers
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["code"] == "task_no_timing"

    code = await completion_code(app_client, business, assignment_id)
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1):
        bad = await app_client.post(
            f"{API}/worker/assignments/{assignment_id}/check-out",
            json={"completion_code": wrong},
            headers=worker.headers,
        )
        assert bad.status_code == 400 and bad.json()["details"]["attempts_left"] == left
    locked = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out",
        json={"completion_code": wrong},
        headers=worker.headers,
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["code"] == "completion_code_locked"
    still_locked = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert still_locked.json()["code"] == "completion_code_locked", still_locked.text
    as_business = (
        await app_client.get(f"{API}/assignments/{assignment_id}", headers=business.headers)
    ).json()
    assert as_business["completion_code"]["locked"] is True
    assert as_business["completion_code"]["can_reissue"] is True

    reissued = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/completion-code/reissue",
        headers=business.headers,
    )
    assert reissued.status_code == 200, reissued.text
    fresh = reissued.json()["completion_code"]
    assert fresh["locked"] is False and fresh["attempts_left"] == 5
    done = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out",
        json={"completion_code": fresh["code"]},
        headers=worker.headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["ended_reason"] == "completed"
    assert done.json()["status"] == "approved"

    reused = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/completion-code/reissue",
        headers=business.headers,
    )
    assert reused.status_code == 409, reused.text

    invoice = await _invoice(app_client, business, shift_id)
    assert _worker_pay(invoice) == TASK
    assert invoice["deposit_applied_minor"] == TASK_SEAT_TOTAL
    assert invoice["amount_due_minor"] == 0


async def test_task_shift_business_confirms_any_time_and_walk_off_pays_nothing(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Task Confirm", online=False)
    shift_id, assignment_id = await _booked_task(app_client, db, business, worker)
    ended = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/end", headers=business.headers
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["ended_reason"] == "completed"
    assert _worker_pay(await _invoice(app_client, business, shift_id)) == TASK

    walker = await make_worker("Task Walker", online=False)
    shift_id, assignment_id = await _booked_task(app_client, db, business, walker)
    stopped = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/stop",
        json={"reason": "worker_left", "note": "Left halfway"},
        headers=business.headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["ended_reason"] == "worker_left"
    assert _worker_pay(await _invoice(app_client, business, shift_id)) == 0


async def test_hourly_shift_code_before_end_is_mutual(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    from tests.integration.test_cancellations import _booked_shift

    business = await make_business()
    worker = await make_worker("Hourly Code", online=False)
    _, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=-timedelta(minutes=30)
    )
    detail = await app_client.get(f"{API}/assignments/{assignment_id}", headers=business.headers)
    checked_in = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-in",
        json={**NEAR, "check_in_code": detail.json()["check_in_code"]},
        headers=worker.headers,
    )
    assert checked_in.status_code == 200, checked_in.text
    out = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out",
        json={"completion_code": await completion_code(app_client, business, assignment_id)},
        headers=worker.headers,
    )
    assert out.status_code == 200, out.text
    assert out.json()["ended_reason"] == "mutual"


# --- Live Work ------------------------------------------------------------------------


def _task_live_body(lat: float, lng: float, total: int) -> dict:
    body = _create_body(lat, lng, pricing_mode="task", task_price_minor=TASK)
    body.pop("hourly_rate_minor")
    body.pop("duration_minutes")
    body["expected_total_minor"] = total
    return body


async def test_task_live_work_end_to_end(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Live Task")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)

    quote = await app_client.post(
        f"{BIZ}/quote",
        json={"category_slug": "house-help", "pricing_mode": "task", "task_price_minor": TASK},
        headers=business.headers,
    )
    assert quote.status_code == 200, quote.text
    q = quote.json()
    assert q["pricing_mode"] == "task" and q["task_price_minor"] == TASK
    assert q["base_amount_minor"] == TASK
    assert q["worker_net_minor"] == TASK - q["commission_minor"]

    created = await app_client.post(
        BIZ, json=_task_live_body(lat, lng, q["total_minor"]), headers=business.headers
    )
    assert created.status_code == 201, created.text
    booking_id = created.json()["booking_id"]
    await _pay(app_client, business, created.json()["deposit_invoice"]["id"])
    accepted = await app_client.post(f"{WRK}/requests/{booking_id}/accept", headers=worker.headers)
    assert accepted.status_code == 200, accepted.text
    assignment_id = accepted.json()["assignment_id"]
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    started = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/start",
        json={"arrival_code": state["arrival_code"]["code"], "latitude": lat, "longitude": lng},
        headers=worker.headers,
    )
    assert started.status_code == 200, started.text

    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["actions"]["can_extend"] is False
    assert state["timer"]["remaining_seconds"] is None
    ext = await app_client.get(
        f"{BIZ}/{booking_id}/extension-quote", params={"minutes": 60}, headers=business.headers
    )
    assert ext.status_code == 409 and ext.json()["code"] == "task_no_timing"

    # Past the reserved window the overdue sweep leaves a task alone.
    await db.execute(
        "UPDATE shifts SET starts_at = now() - interval '20 hours',"
        " ends_at = now() - interval '8 hours' WHERE id = $1",
        UUID(booking_id),
    )
    await run_sweep_once(get_pool())
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["status"] == "in_progress"

    code = await live_completion_code(app_client, business, booking_id)
    wrong = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/complete",
        json={"completion_code": "000000" if code != "000000" else "111111"},
        headers=worker.headers,
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "completion_code_invalid"
    done = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/complete",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["earnings"]["total_net_minor"] == q["worker_net_minor"]
