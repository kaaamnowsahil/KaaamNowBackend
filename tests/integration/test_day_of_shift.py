"""Day-of-shift: per-booking code, extensions with overtime, business stop / worker walk-off
(rules §7–§10). Booking: ₹120/h × 4h30m = ₹540 per seat, ₹572.83 paid at posting."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import httpx

from app.db.pool import get_pool
from app.services.shifts.shift_sweeps import prompt_extensions
from tests.integration.test_cancellations import BOOKING, _balance, _booked_shift, _vouchers

API = "/api/v1"
NEAR = {"latitude": 28.6316, "longitude": 77.2168}


async def _check_in(client: httpx.AsyncClient, business, worker, assignment_id: str) -> None:  # type: ignore[no-untyped-def]
    detail = await client.get(f"{API}/assignments/{assignment_id}", headers=business.headers)
    resp = await client.post(
        f"{API}/worker/assignments/{assignment_id}/check-in",
        json={**NEAR, "check_in_code": detail.json()["check_in_code"]},
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text


async def _invoice(client: httpx.AsyncClient, business, shift_id: str) -> dict:  # type: ignore[no-untyped-def]
    resp = await client.post(f"{API}/business/shifts/{shift_id}/invoice", headers=business.headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def test_extension_prompt_accept_and_overtime_pay(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Overtime Worker", online=False)
    shift_id, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=-timedelta(minutes=290)
    )
    await _check_in(app_client, business, worker, assignment_id)

    assert await prompt_extensions(get_pool()) >= 1
    assert await db.fetchval(
        "SELECT count(*) FROM notifications WHERE user_id = $1 AND kind = 'extension_prompt'",
        business.user_id,
    )

    asked = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/extensions",
        json={"extra_minutes": 60},
        headers=business.headers,
    )
    assert asked.status_code == 201, asked.text
    again = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/extensions",
        json={"extra_minutes": 30},
        headers=business.headers,
    )
    assert again.status_code == 409, again.text
    detail = (
        await app_client.get(f"{API}/assignments/{assignment_id}", headers=worker.headers)
    ).json()
    assert detail["pending_extension"]["id"] == asked.json()["id"]

    accepted = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/extensions/{asked.json()['id']}/accept",
        headers=worker.headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["extended_minutes"] == 60
    assert accepted.json()["pending_extension"] is None
    assert accepted.json()["can_end"] is False

    # Jump to the extended end: worked the full booking plus the hour.
    await db.execute(
        "UPDATE shifts SET starts_at = starts_at - interval '70 minutes',"
        " ends_at = ends_at - interval '70 minutes' WHERE id = $1",
        UUID(shift_id),
    )
    await db.execute(
        "UPDATE attendance_records ar SET checked_in_at = s.starts_at"
        " FROM shift_assignments a JOIN shifts s ON s.id = a.shift_id"
        " WHERE ar.assignment_id = a.id AND a.id = $1",
        UUID(assignment_id),
    )
    out = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out", json={}, headers=worker.headers
    )
    assert out.status_code == 200, out.text
    too_much = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/attendance/approve",
        json={"approved_minutes": 331},
        headers=business.headers,
    )
    assert too_much.status_code == 400, too_much.text
    approved = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/attendance/approve",
        json={"approved_minutes": 330},
        headers=business.headers,
    )
    assert approved.status_code == 200, approved.text

    invoice = await _invoice(app_client, business, shift_id)
    # 270 min at ₹120/h = ₹540, plus 60 min at 130% = ₹156.
    assert invoice["worker_subtotal_minor"] == BOOKING + 15600
    assert invoice["amount_due_minor"] > 0


async def test_business_stop_pays_worker_eighty_percent(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Stopped Worker", online=False)
    shift_id, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=-timedelta(minutes=60)
    )
    await _check_in(app_client, business, worker, assignment_id)
    early = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/end", headers=business.headers
    )
    assert early.status_code == 409, early.text

    stopped = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/stop",
        json={"reason": "business_stopped"},
        headers=business.headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "approved"
    assert stopped.json()["ended_reason"] == "business_stopped"

    invoice = await _invoice(app_client, business, shift_id)
    assert invoice["worker_subtotal_minor"] == BOOKING
    assert invoice["status"] == "paid"
    assert await _balance(app_client, worker) == BOOKING * 80 // 100


async def test_worker_walk_off_fee_and_voucher(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Walkoff Worker", online=False)
    _, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=-timedelta(minutes=60)
    )
    await _check_in(app_client, business, worker, assignment_id)
    left = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/stop",
        json={"reason": "worker_left"},
        headers=business.headers,
    )
    assert left.status_code == 200, left.text
    assert left.json()["status"] == "checked_out"
    assert left.json()["ended_reason"] == "worker_left"
    assert await _balance(app_client, worker) == -BOOKING // 2
    assert await _vouchers(db, business) == 1
