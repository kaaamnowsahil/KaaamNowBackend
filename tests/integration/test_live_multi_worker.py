"""Live Work with several Workers: deposit = one Worker's total × N, the coupon split once
across the booking, partial fills refunding the empty seats, one-Worker cancellations on both
sides, per-Worker completion and whole-booking cancel with empty seats.

Prices are the seed defaults used by ``test_live_work``: one Worker costs ``TOTAL`` paise.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from app.services.background.background_sweep_loop import run_sweep_once
from tests.integration.conftest import Actor
from tests.integration.test_coupons import _code, _coupon
from tests.integration.test_live_work import (
    BASE,
    BIZ,
    COMMISSION,
    MINUTES,
    RATE,
    TOTAL,
    WRK,
    _create_body,
    _ledger,
    _location,
    _pay,
    _place_worker,
    _worked,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _state(client: httpx.AsyncClient, business: Actor, booking_id: str) -> dict:
    resp = await client.get(f"{BIZ}/{booking_id}", headers=business.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _searching_for(
    client: httpx.AsyncClient, business: Actor, lat: float, lng: float, workers: int
) -> dict:
    body = _create_body(lat, lng, workers_required=workers, expected_total_minor=TOTAL * workers)
    posted = await client.post(BIZ, json=body, headers=business.headers)
    assert posted.status_code == 201, posted.text
    await _pay(client, business, posted.json()["deposit_invoice"]["id"])
    state = await _state(client, business, posted.json()["booking_id"])
    assert state["status"] == "searching", state
    return state


async def _accept(client: httpx.AsyncClient, worker: Actor, booking_id: str) -> str:
    resp = await client.post(f"{WRK}/requests/{booking_id}/accept", headers=worker.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["assignment_id"]


def _seat(state: dict, assignment_id: str) -> dict:
    return next(s for s in state["workers"] if s["assignment"]["assignment_id"] == assignment_id)


async def _start(
    client: httpx.AsyncClient,
    business: Actor,
    worker: Actor,
    booking_id: str,
    assignment_id: str,
    lat: float,
    lng: float,
) -> None:
    code = _seat(await _state(client, business, booking_id), assignment_id)["arrival_code"]["code"]
    resp = await client.post(
        f"{WRK}/bookings/{assignment_id}/start",
        json={"arrival_code": code, "latitude": lat, "longitude": lng},
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text


async def _workers(make_worker, lat: float, lng: float, client: httpx.AsyncClient, n: int):  # type: ignore[no-untyped-def]
    workers = [await make_worker(f"Crew {i + 1}") for i in range(n)]
    for worker in workers:
        await _place_worker(client, worker, lat, lng)
    return workers


async def _shift_seats(db: asyncpg.Connection, booking_id: str) -> int:
    return await db.fetchval("SELECT workers_required FROM shifts WHERE id = $1", UUID(booking_id))


# --- pricing ------------------------------------------------------------------------------


async def test_quote_and_deposit_scale_with_workers(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    quote = await app_client.post(
        f"{BIZ}/quote",
        json={"hourly_rate_minor": RATE, "duration_minutes": MINUTES, "workers_required": 3},
        headers=business.headers,
    )
    assert quote.status_code == 200, quote.text
    q = quote.json()
    assert q["total_minor"] == TOTAL
    assert q["workers_required"] == 3
    assert q["booking_total_minor"] == TOTAL * 3
    assert q["max_workers"] == 10

    single = await app_client.post(
        f"{BIZ}/quote",
        json={"hourly_rate_minor": RATE, "duration_minutes": MINUTES},
        headers=business.headers,
    )
    assert single.json()["workers_required"] == 1
    assert single.json()["booking_total_minor"] == TOTAL

    too_many = await app_client.post(
        f"{BIZ}/quote",
        json={"hourly_rate_minor": RATE, "duration_minutes": MINUTES, "workers_required": 11},
        headers=business.headers,
    )
    assert too_many.status_code == 400, too_many.text
    assert "workers_required" in too_many.json()["details"]["fields"]

    lat, lng = _location()
    stale = await app_client.post(
        BIZ, json=_create_body(lat, lng, workers_required=3), headers=business.headers
    )
    assert stale.status_code == 409
    assert stale.json()["details"]["total_minor"] == TOTAL * 3

    posted = await app_client.post(
        BIZ,
        json=_create_body(lat, lng, workers_required=3, expected_total_minor=TOTAL * 3),
        headers=business.headers,
    )
    assert posted.status_code == 201, posted.text
    booking = posted.json()
    assert booking["workers_required"] == 3
    assert booking["workers_filled"] == 0
    assert booking["seat_total_minor"] == TOTAL
    assert booking["deposit_invoice"]["total_minor"] == TOTAL * 3
    assert booking["workers"] == []
    lines = await db.fetch(
        "SELECT line_kind, amount_minor FROM shift_invoice_lines WHERE invoice_id = $1",
        UUID(booking["deposit_invoice"]["id"]),
    )
    assert sum(r["amount_minor"] for r in lines) == TOTAL * 3
    assert await _shift_seats(db, booking["booking_id"]) == 3


async def test_flat_coupon_is_split_once_across_the_workers(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    code = _code("CREW")
    # ₹50 off the commission. One Worker's commission is ₹40, so alone it would cap at ₹40;
    # on 3 Workers (₹120 commission) the ₹50 is taken once and split: ₹16.66 per Worker.
    await _coupon(db, code, discount_type="flat", discount_value=50)
    quote = await app_client.post(
        f"{BIZ}/quote",
        json={
            "hourly_rate_minor": RATE,
            "duration_minutes": MINUTES,
            "workers_required": 3,
            "promo_code": code,
        },
        headers=business.headers,
    )
    assert quote.status_code == 200, quote.text
    q = quote.json()
    assert q["promo_discount_minor"] == 5000 // 3
    assert q["booking_total_minor"] == q["total_minor"] * 3
    assert q["total_minor"] < TOTAL

    lat, lng = _location()
    posted = await app_client.post(
        BIZ,
        json=_create_body(
            lat,
            lng,
            workers_required=3,
            promo_code=code,
            expected_total_minor=q["booking_total_minor"],
        ),
        headers=business.headers,
    )
    assert posted.status_code == 201, posted.text
    booking = posted.json()
    assert booking["deposit_invoice"]["total_minor"] == q["booking_total_minor"]
    await _pay(app_client, business, booking["deposit_invoice"]["id"])
    redemption = await db.fetchrow(
        "SELECT status, discount_minor FROM promo_redemptions WHERE shift_id = $1",
        UUID(booking["booking_id"]),
    )
    assert redemption["status"] == "applied"
    assert redemption["discount_minor"] == (5000 // 3) * 3


# --- search ---------------------------------------------------------------------------------


async def test_partial_fill_refunds_the_empty_seats(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    first, second = await _workers(make_worker, lat, lng, app_client, 2)
    booking = await _searching_for(app_client, business, lat, lng, 3)
    booking_id = booking["booking_id"]
    await _accept(app_client, first, booking_id)
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "searching"
    assert state["workers_filled"] == 1 and len(state["workers"]) == 1
    await _accept(app_client, second, booking_id)

    await db.execute(
        "UPDATE shifts SET search_expires_at = now() - interval '1 second' WHERE id = $1",
        UUID(booking_id),
    )
    await run_sweep_once(get_pool())
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "assigned"
    assert state["workers_required"] == 3
    assert state["workers_filled"] == 2
    assert state["unfilled_refund_minor"] == TOTAL
    assert [(r["amount_minor"], r["reason"], r["status"]) for r in state["refunds"]] == [
        (TOTAL, "unfilled_seats", "processed")
    ]
    assert await _shift_seats(db, booking_id) == 2
    title = await db.fetchval(
        "SELECT title FROM notifications WHERE user_id = $1 AND data->>'shift_id' = $2"
        " AND title LIKE '%Workers found' ORDER BY created_at DESC LIMIT 1",
        business.user_id,
        booking_id,
    )
    assert title == "2 of 3 Workers found"

    await run_sweep_once(get_pool())
    again = await _state(app_client, business, booking_id)
    assert len(again["refunds"]) == 1


async def test_whole_booking_cancel_refunds_empty_seats_too(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker
) -> None:
    business = await make_business()
    lat, lng = _location()
    (worker,) = await _workers(make_worker, lat, lng, app_client, 1)
    booking = await _searching_for(app_client, business, lat, lng, 3)
    booking_id = booking["booking_id"]
    assignment_id = await _accept(app_client, worker, booking_id)

    preview = (
        await app_client.get(f"{BIZ}/{booking_id}/cancel-preview", headers=business.headers)
    ).json()
    assert preview["business_refund_minor"] + preview["business_retained_minor"] == TOTAL * 3
    assert preview["business_refund_minor"] >= TOTAL * 2
    cancelled = await app_client.post(
        f"{BIZ}/{booking_id}/cancel",
        json={"reason": "Event moved", "expected_refund_minor": preview["business_refund_minor"]},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert sum(r["amount_minor"] for r in body["refunds"]) == preview["business_refund_minor"]
    worker_view = (
        await app_client.get(f"{WRK}/bookings/{assignment_id}", headers=worker.headers)
    ).json()
    assert worker_view["status"] == "cancelled"


# --- one Worker at a time ----------------------------------------------------------------


async def test_business_cancels_one_worker_then_the_last(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    first, second = await _workers(make_worker, lat, lng, app_client, 2)
    booking = await _searching_for(app_client, business, lat, lng, 2)
    booking_id = booking["booking_id"]
    first_id = await _accept(app_client, first, booking_id)
    second_id = await _accept(app_client, second, booking_id)
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "assigned"
    assert _seat(state, first_id)["actions"]["can_cancel"] is True

    preview = await app_client.get(
        f"{BIZ}/{booking_id}/workers/{first_id}/cancel-preview", headers=business.headers
    )
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p["business_refund_minor"] + p["business_retained_minor"] == TOTAL
    cancelled = await app_client.post(
        f"{BIZ}/{booking_id}/workers/{first_id}/cancel",
        json={"reason": "Need fewer hands", "expected_refund_minor": p["business_refund_minor"]},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    state = cancelled.json()
    assert state["status"] == "assigned"
    assert state["workers_filled"] == 1
    assert [s["assignment"]["assignment_id"] for s in state["workers"]] == [second_id]
    assert sum(r["amount_minor"] for r in state["refunds"]) == p["business_refund_minor"]
    assert await _shift_seats(db, booking_id) == 1
    first_view = (await app_client.get(f"{WRK}/bookings/{first_id}", headers=first.headers)).json()
    assert first_view["status"] == "cancelled"
    second_view = (
        await app_client.get(f"{WRK}/bookings/{second_id}", headers=second.headers)
    ).json()
    assert second_view["status"] == "assigned"

    repeat = await app_client.post(
        f"{BIZ}/{booking_id}/workers/{first_id}/cancel", json={}, headers=business.headers
    )
    assert repeat.status_code == 200
    assert len(repeat.json()["refunds"]) == len(state["refunds"])

    last_preview = (
        await app_client.get(
            f"{BIZ}/{booking_id}/workers/{second_id}/cancel-preview", headers=business.headers
        )
    ).json()
    last = await app_client.post(
        f"{BIZ}/{booking_id}/workers/{second_id}/cancel", json={}, headers=business.headers
    )
    assert last.status_code == 200, last.text
    assert last.json()["status"] == "cancelled"
    assert sum(r["amount_minor"] for r in last.json()["refunds"]) == (
        p["business_refund_minor"] + last_preview["business_refund_minor"]
    )


async def test_worker_cancel_reopens_the_seat_while_nobody_started(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    first, second = await _workers(make_worker, lat, lng, app_client, 2)
    booking = await _searching_for(app_client, business, lat, lng, 2)
    booking_id = booking["booking_id"]
    first_id = await _accept(app_client, first, booking_id)
    await _accept(app_client, second, booking_id)
    assert (await _state(app_client, business, booking_id))["status"] == "assigned"

    cancelled = await app_client.post(
        f"{WRK}/bookings/{first_id}/cancel", json={"reason": "Clash"}, headers=first.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "searching"
    assert state["refunds"] == []
    assert state["workers_filled"] == 1
    assert await _shift_seats(db, booking_id) == 2


async def test_worker_cancel_after_another_started_refunds_the_seat(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    first, second = await _workers(make_worker, lat, lng, app_client, 2)
    booking = await _searching_for(app_client, business, lat, lng, 2)
    booking_id = booking["booking_id"]
    first_id = await _accept(app_client, first, booking_id)
    second_id = await _accept(app_client, second, booking_id)
    await _start(app_client, business, second, booking_id, second_id, lat, lng)
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "in_progress"
    assert state["actions"]["can_cancel"] is True  # a force-cancel for the Worker who started

    cancelled = await app_client.post(
        f"{WRK}/bookings/{first_id}/cancel", json={}, headers=first.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "in_progress"
    assert [(r["amount_minor"], r["reason"]) for r in state["refunds"]] == [
        (TOTAL, "seat_released")
    ]
    assert await _shift_seats(db, booking_id) == 1
    assert [s["assignment"]["assignment_id"] for s in state["workers"]] == [second_id]


# --- completion ---------------------------------------------------------------------------


async def test_each_worker_completes_and_the_booking_ends_after_the_last(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    first, second = await _workers(make_worker, lat, lng, app_client, 2)
    booking = await _searching_for(app_client, business, lat, lng, 2)
    booking_id = booking["booking_id"]
    first_id = await _accept(app_client, first, booking_id)
    second_id = await _accept(app_client, second, booking_id)
    await _start(app_client, business, first, booking_id, first_id, lat, lng)
    await _start(app_client, business, second, booking_id, second_id, lat, lng)

    state = await _state(app_client, business, booking_id)
    assert state["status"] == "in_progress"
    first_seat = _seat(state, first_id)
    assert first_seat["timer"]["remaining_seconds"] > MINUTES * 60 - 120
    assert first_seat["actions"]["can_end_work"] is True
    worker_view = (await app_client.get(f"{WRK}/bookings/{first_id}", headers=first.headers)).json()
    assert worker_view["workers_required"] == 2

    await _worked(db, first_id, MINUTES)
    code = first_seat["completion_code"]["code"]
    done = await app_client.post(
        f"{WRK}/bookings/{first_id}/complete",
        json={"completion_code": code},
        headers=first.headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "in_progress"

    ended = await app_client.post(
        f"{BIZ}/{booking_id}/end",
        params={"assignment_id": second_id},
        headers=business.headers,
    )
    assert ended.status_code == 200, ended.text
    state = ended.json()
    assert state["status"] == "completed"
    assert state["refunds"] == []
    finals = [s["final_invoice"] for s in state["workers"]]
    assert [(f["status"], f["total_minor"]) for f in finals] == [("paid", TOTAL)] * 2
    assert finals[0]["id"] != finals[1]["id"]
    assert await _ledger(db, first_id) == {"shift_earning": BASE, "commission": -COMMISSION}
    # Ended by the Business without the code: a force-cancel, the Worker keeps 80%.
    assert sum((await _ledger(db, second_id)).values()) == BASE * 80 // 100


async def test_single_worker_booking_is_unchanged(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker
) -> None:
    business = await make_business()
    lat, lng = _location()
    (worker,) = await _workers(make_worker, lat, lng, app_client, 1)
    posted = await app_client.post(BIZ, json=_create_body(lat, lng), headers=business.headers)
    assert posted.status_code == 201, posted.text
    booking_id = posted.json()["booking_id"]
    assert posted.json()["workers_required"] == 1
    await _pay(app_client, business, posted.json()["deposit_invoice"]["id"])
    assignment_id = await _accept(app_client, worker, booking_id)
    state = await _state(app_client, business, booking_id)
    assert state["status"] == "assigned"
    assert state["assignment"]["assignment_id"] == assignment_id
    assert state["arrival_code"]["code"]
    assert len(state["workers"]) == 1
    assert state["unfilled_refund_minor"] == 0
