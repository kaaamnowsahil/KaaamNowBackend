"""Live Work end to end: post → pay → search → accept → arrival code → extend → complete,
cancellations on both sides, no-worker refunds, sweeps, admin pricing + audit.

Default Live pricing (seed v1): commission 4%, tax 2% on (base + commission), extension
surcharge 30%. ₹500/h × 2h → base 1,00,000 · commission 4,000 · tax 2,080 · total 1,06,080 paise.
Every test works at its own far-away location so offers never reach other tests' Workers.
"""

from __future__ import annotations

import asyncio
import itertools
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from app.services.background.background_sweep_loop import run_sweep_once
from tests.integration.conftest import Actor, live_completion_code
from tests.integration.test_admin_crud import _admin

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
BIZ = f"{API}/business/live-work"
WRK = f"{API}/worker/live-work"
ADM = f"{API}/admin/live-work"
RATE = 50000
MINUTES = 120
BASE, COMMISSION, TAX, TOTAL = 100000, 4000, 2080, 106080
WORKER_NET = BASE - COMMISSION

_spot = itertools.count(1)


def _location() -> tuple[float, float]:
    """A spot ~50 km from every other test's spot (outside any search radius)."""
    n = next(_spot)
    return 8.5 + n * 0.5, 74.0 + (n % 3) * 0.5


async def _place_worker(client: httpx.AsyncClient, worker: Actor, lat: float, lng: float) -> None:
    resp = await client.put(
        f"{API}/me/availability",
        json={"is_available": True, "latitude": lat, "longitude": lng},
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text


def _create_body(lat: float, lng: float, **overrides: object) -> dict:
    body: dict = {
        "category_slug": "house-help",
        "job_title": "Kitchen help",
        "description": "Prep and wash-up for lunch service.",
        "address_text": "Test kitchen, Live Street",
        "latitude": lat,
        "longitude": lng,
        "arrival_instructions": "Use the side door.",
        "site_contact_name": "Manager",
        "duration_minutes": MINUTES,
        "hourly_rate_minor": RATE,
        "accept_terms": True,
        "expected_total_minor": TOTAL,
    }
    body.update(overrides)
    return body


async def _pay(client: httpx.AsyncClient, business: Actor, invoice_id: str) -> dict:
    payment = await client.post(
        f"{API}/business/invoices/{invoice_id}/payments",
        json={"method": "upi_qr"},
        headers=business.headers,
    )
    assert payment.status_code == 201, payment.text
    confirmed = await client.post(
        f"{API}/business/payments/{payment.json()['id']}/confirm", headers=business.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "succeeded", confirmed.text
    return payment.json()


async def _posted(client: httpx.AsyncClient, business: Actor, lat: float, lng: float) -> dict:
    resp = await client.post(BIZ, json=_create_body(lat, lng), headers=business.headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _searching(client: httpx.AsyncClient, business: Actor, lat: float, lng: float) -> dict:
    booking = await _posted(client, business, lat, lng)
    await _pay(client, business, booking["deposit_invoice"]["id"])
    state = await client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    assert state.json()["status"] == "searching", state.text
    return state.json()


async def _accepted(
    client: httpx.AsyncClient, business: Actor, worker: Actor, lat: float, lng: float
) -> tuple[dict, dict]:
    booking = await _searching(client, business, lat, lng)
    accepted = await client.post(
        f"{WRK}/requests/{booking['booking_id']}/accept", headers=worker.headers
    )
    assert accepted.status_code == 200, accepted.text
    state = await client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    return state.json(), accepted.json()


async def _started(
    client: httpx.AsyncClient, business: Actor, worker: Actor, lat: float, lng: float
) -> tuple[dict, dict]:
    booking, job = await _accepted(client, business, worker, lat, lng)
    started = await client.post(
        f"{WRK}/bookings/{job['assignment_id']}/start",
        json={"arrival_code": booking["arrival_code"]["code"], "latitude": lat, "longitude": lng},
        headers=worker.headers,
    )
    assert started.status_code == 200, started.text
    return booking, started.json()


async def _ledger(db: asyncpg.Connection, assignment_id: str) -> dict[str, int]:
    rows = await db.fetch(
        "SELECT entry_type, SUM(amount_minor) AS total FROM earning_ledger_entries "
        "WHERE assignment_id = $1 GROUP BY entry_type",
        UUID(assignment_id),
    )
    return {r["entry_type"]: int(r["total"]) for r in rows}


# --- pricing + validation -------------------------------------------------------------


async def test_quote_and_inline_validation(app_client, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    quote = await app_client.post(
        f"{BIZ}/quote",
        json={"category_slug": "house-help", "hourly_rate_minor": RATE, "duration_minutes": 120},
        headers=business.headers,
    )
    assert quote.status_code == 200, quote.text
    q = quote.json()
    assert (q["base_amount_minor"], q["commission_minor"], q["tax_minor"], q["total_minor"]) == (
        BASE,
        COMMISSION,
        TAX,
        TOTAL,
    )
    assert q["tax_base"] == "subtotal" and q["taxable_minor"] == BASE + COMMISSION
    assert q["tax_label"] == "Tax"
    assert q["worker_net_minor"] == WORKER_NET
    assert q["extension_rate_minor"] == 65000

    bad = await app_client.post(
        f"{BIZ}/quote",
        json={"hourly_rate_minor": RATE, "duration_minutes": 45},
        headers=business.headers,
    )
    assert bad.status_code == 400
    assert "duration_minutes" in bad.json()["details"]["fields"]
    assert bad.json()["request_id"]

    lat, lng = _location()
    missing = await app_client.post(
        BIZ,
        json=_create_body(lat, lng, accept_terms=False, duration_minutes=50),
        headers=business.headers,
    )
    assert missing.status_code == 400
    assert set(missing.json()["details"]["fields"]) == {"accept_terms", "duration_minutes"}

    stale = await app_client.post(
        BIZ, json=_create_body(lat, lng, expected_total_minor=TOTAL - 1), headers=business.headers
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "price_changed"
    assert stale.json()["details"]["total_minor"] == TOTAL


async def test_post_is_idempotent_and_waits_for_payment(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    lat, lng = _location()
    body = _create_body(lat, lng, idempotency_key="live-post-key-0001")
    first = await app_client.post(BIZ, json=body, headers=business.headers)
    second = await app_client.post(BIZ, json=body, headers=business.headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["booking_id"] == second.json()["booking_id"]
    booking = first.json()
    assert booking["status"] == "awaiting_payment"
    assert booking["deposit_invoice"]["total_minor"] == TOTAL
    assert booking["actions"]["can_pay"] is True
    offers = await db.fetchval(
        "SELECT count(*) FROM live_dispatches WHERE shift_id = $1", UUID(booking["booking_id"])
    )
    assert offers == 0
    lines = await db.fetch(
        "SELECT line_kind, amount_minor FROM shift_invoice_lines WHERE invoice_id = $1",
        UUID(booking["deposit_invoice"]["id"]),
    )
    assert sorted((r["line_kind"], r["amount_minor"]) for r in lines) == sorted(
        [("worker_pay", BASE), ("platform_fee", COMMISSION), ("tax", TAX)]
    )


# --- happy path -------------------------------------------------------------------------


async def test_full_live_work_flow(app_client, make_business, make_worker, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker("Live One")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)

    available = await app_client.get(
        f"{BIZ}/available-workers",
        params={"lat": lat, "lng": lng, "category": "house-help"},
        headers=business.headers,
    )
    assert available.status_code == 200, available.text
    assert available.json()["count"] == 1

    booking = await _searching(app_client, business, lat, lng)
    booking_id = booking["booking_id"]
    assert booking["search"]["notified_workers"] == 1

    requests = (await app_client.get(f"{WRK}/requests", headers=worker.headers)).json()
    offer = next(r for r in requests if r["booking_id"] == booking_id)
    assert offer["worker_net_minor"] == WORKER_NET
    assert "arrival_code" not in str(offer)

    accepted = await app_client.post(f"{WRK}/requests/{booking_id}/accept", headers=worker.headers)
    assert accepted.status_code == 200, accepted.text
    job = accepted.json()
    assignment_id = job["assignment_id"]
    assert job["status"] == "assigned"
    assert "code" not in (job["arrival"] or {})

    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["status"] == "assigned"
    assert state["assignment"]["worker"]["full_name"] == "Live One"
    code = state["arrival_code"]["code"]
    assert len(code) == 6 and state["arrival_code"]["attempts_left"] == 5

    # Generic Shift endpoints refuse Live Work bookings.
    generic = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/end", headers=business.headers
    )
    assert generic.status_code == 409
    assert generic.json()["code"] == "live_work_action_required"

    travel = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/start-travel", headers=worker.headers
    )
    assert travel.status_code == 200 and travel.json()["status"] == "en_route"
    located = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/location",
        json={"latitude": lat + 0.01, "longitude": lng, "accuracy_m": 15},
        headers=worker.headers,
    )
    assert located.status_code == 200, located.text
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["status"] == "en_route"
    assert state["assignment"]["location_status"] == "live"
    assert 1.0 < state["assignment"]["location"]["distance_km"] < 1.3

    too_far = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/start",
        json={"arrival_code": code, "latitude": lat + 0.01, "longitude": lng},
        headers=worker.headers,
    )
    assert too_far.status_code == 400 and too_far.json()["code"] == "check_in_too_far"
    wrong = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/start",
        json={
            "arrival_code": "ZZZZZZ" if code != "ZZZZZZ" else "YYYYYY",
            "latitude": lat,
            "longitude": lng,
        },
        headers=worker.headers,
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "arrival_code_invalid"
    assert wrong.json()["details"]["attempts_left"] == 4

    start_body = {"arrival_code": code.lower(), "latitude": lat, "longitude": lng}
    started = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/start", json=start_body, headers=worker.headers
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    again = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/start", json=start_body, headers=worker.headers
    )
    assert again.status_code == 200 and again.json()["status"] == "in_progress"
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["status"] == "in_progress"
    assert state["timer"]["remaining_seconds"] > MINUTES * 60 - 120

    # Extension: 60 min at ₹650/h (30% surcharge) + commission + tax.
    ext_quote = await app_client.get(
        f"{BIZ}/{booking_id}/extension-quote", params={"minutes": 60}, headers=business.headers
    )
    assert ext_quote.status_code == 200, ext_quote.text
    eq = ext_quote.json()
    assert eq["extension_rate_minor"] == 65000
    assert (eq["additional_base_minor"], eq["commission_minor"], eq["tax_minor"]) == (
        65000,
        2600,
        1352,
    )
    assert eq["additional_total_minor"] == 68952
    assert eq["revised_minutes"] == 180 and eq["revised_total_minor"] == TOTAL + 68952

    requested = await app_client.post(
        f"{BIZ}/{booking_id}/extensions",
        json={"extra_minutes": 60, "expected_total_minor": 68952},
        headers=business.headers,
    )
    assert requested.status_code == 201, requested.text
    ext_id = requested.json()["extensions"][-1]["id"]
    answered = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/extensions/{ext_id}",
        json={"accept": True},
        headers=worker.headers,
    )
    assert answered.status_code == 200, answered.text
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    ext = state["extensions"][-1]
    assert ext["status"] == "awaiting_payment"
    await _pay(app_client, business, ext["invoice_id"])
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["extensions"][-1]["status"] == "applied"
    assert state["timer"]["extended_minutes"] == 60

    no_code = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/complete", headers=worker.headers
    )
    assert no_code.status_code == 422, no_code.text
    assert state["completion_code"]["code"]
    worker_view = (
        await app_client.get(f"{WRK}/bookings/{assignment_id}", headers=worker.headers)
    ).json()
    assert worker_view["completion"]["code"] is None
    # Worked the whole reserved + extra time, so all of it is billed.
    await db.execute(
        "UPDATE attendance_records SET checked_in_at = $2 WHERE assignment_id = $1",
        UUID(assignment_id),
        datetime.now(UTC) - timedelta(minutes=MINUTES + 61),
    )
    code = await live_completion_code(app_client, business, booking_id)
    done = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/complete",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["earnings"]["total_net_minor"] == WORKER_NET + 62400
    again = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/complete",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert again.status_code == 200

    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["status"] == "completed"
    final = state["final_invoice"]
    assert final["status"] == "paid"
    assert final["total_minor"] == TOTAL + 68952
    assert final["amount_due_minor"] == 0 and final["refund_due_minor"] == 0
    assert state["refunds"] == []
    assert await _ledger(db, assignment_id) == {
        "shift_earning": BASE + 65000,
        "commission": -(COMMISSION + 2600),
    }


async def test_only_one_worker_wins_a_race(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    lat, lng = _location()
    first, second = await make_worker("Racer A"), await make_worker("Racer B")
    for w in (first, second):
        await _place_worker(app_client, w, lat, lng)
    booking = await _searching(app_client, business, lat, lng)
    assert booking["search"]["notified_workers"] == 2
    url = f"{WRK}/requests/{booking['booking_id']}/accept"
    results = await asyncio.gather(
        app_client.post(url, headers=first.headers), app_client.post(url, headers=second.headers)
    )
    codes = sorted(r.status_code for r in results)
    assert codes[0] == 200 and codes[1] in (404, 409), [r.text for r in results]
    state = (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    ).json()
    assert state["status"] == "assigned"


async def test_arrival_code_locks_and_can_be_reissued(
    app_client, make_business, make_worker
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker("Code Tester")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _accepted(app_client, business, worker, lat, lng)
    url = f"{WRK}/bookings/{job['assignment_id']}/start"
    wrong = "AAAAAA" if booking["arrival_code"]["code"] != "AAAAAA" else "BBBBBB"
    for _ in range(4):
        resp = await app_client.post(
            url,
            json={"arrival_code": wrong, "latitude": lat, "longitude": lng},
            headers=worker.headers,
        )
        assert resp.json()["code"] == "arrival_code_invalid"
    locked = await app_client.post(
        url, json={"arrival_code": wrong, "latitude": lat, "longitude": lng}, headers=worker.headers
    )
    assert locked.status_code == 409 and locked.json()["code"] == "arrival_code_locked"
    right = await app_client.post(
        url,
        json={"arrival_code": booking["arrival_code"]["code"], "latitude": lat, "longitude": lng},
        headers=worker.headers,
    )
    assert right.json()["code"] == "arrival_code_locked"

    reissued = await app_client.post(
        f"{BIZ}/{booking['booking_id']}/arrival-code/reissue", headers=business.headers
    )
    assert reissued.status_code == 200, reissued.text
    new_code = reissued.json()["arrival_code"]
    assert new_code["locked"] is False and new_code["attempts_left"] == 5
    ok = await app_client.post(
        url,
        json={"arrival_code": new_code["code"], "latitude": lat, "longitude": lng},
        headers=worker.headers,
    )
    assert ok.status_code == 200 and ok.json()["status"] == "in_progress"


# --- cancellations + refunds ------------------------------------------------------------


async def test_business_cancel_before_payment_and_before_acceptance(
    app_client, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    lat, lng = _location()
    unpaid = await _posted(app_client, business, lat, lng)
    preview = await app_client.get(
        f"{BIZ}/{unpaid['booking_id']}/cancel-preview", headers=business.headers
    )
    assert preview.json()["stage"] == "before_payment"
    assert preview.json()["fee_minor"] == 0
    cancelled = await app_client.post(
        f"{BIZ}/{unpaid['booking_id']}/cancel", json={"reason": "Typo"}, headers=business.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["deposit_invoice"]["status"] == "void"

    searching = await _searching(app_client, business, lat, lng)
    preview = await app_client.get(
        f"{BIZ}/{searching['booking_id']}/cancel-preview", headers=business.headers
    )
    assert preview.json()["stage"] == "before_acceptance"
    assert preview.json()["business_refund_minor"] == TOTAL
    stale = await app_client.post(
        f"{BIZ}/{searching['booking_id']}/cancel",
        json={"expected_refund_minor": TOTAL - 1},
        headers=business.headers,
    )
    assert stale.status_code == 409
    cancelled = await app_client.post(
        f"{BIZ}/{searching['booking_id']}/cancel",
        json={"expected_refund_minor": TOTAL},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["cancellation"]["cancelled_by"] == "business"
    assert [(r["amount_minor"], r["status"]) for r in body["refunds"]] == [(TOTAL, "processed")]
    repeat = await app_client.post(
        f"{BIZ}/{searching['booking_id']}/cancel", json={}, headers=business.headers
    )
    assert repeat.status_code == 200 and len(repeat.json()["refunds"]) == 1


async def test_business_cancel_before_the_arrival_code_is_free(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Cancelled On")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _accepted(app_client, business, worker, lat, lng)
    preview = (
        await app_client.get(
            f"{BIZ}/{booking['booking_id']}/cancel-preview", headers=business.headers
        )
    ).json()
    assert preview["stage"] == "before_start"
    assert preview["fee_minor"] == 0 and preview["worker_compensation_minor"] == 0
    assert preview["business_refund_minor"] == TOTAL
    cancelled = await app_client.post(
        f"{BIZ}/{booking['booking_id']}/cancel",
        json={"reason": "Plans changed", "expected_refund_minor": preview["business_refund_minor"]},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    refunds = cancelled.json()["refunds"]
    assert sum(r["amount_minor"] for r in refunds) == preview["business_refund_minor"]
    charge = await db.fetchrow(
        "SELECT * FROM cancellation_charges WHERE assignment_id = $1", UUID(job["assignment_id"])
    )
    assert charge["party"] == "business"
    assert charge["worker_compensation_minor"] == 0
    assert sum((await _ledger(db, job["assignment_id"])).values()) == 0
    worker_view = (
        await app_client.get(f"{WRK}/bookings/{job['assignment_id']}", headers=worker.headers)
    ).json()
    assert worker_view["status"] == "cancelled"
    assert worker_view["cancellation"]["cancelled_by"] == "business"


async def test_worker_cancel_before_start_reopens_search(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Backs Out")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _accepted(app_client, business, worker, lat, lng)
    preview = (
        await app_client.get(
            f"{WRK}/bookings/{job['assignment_id']}/cancel-preview", headers=worker.headers
        )
    ).json()
    assert preview["party"] == "worker" and preview["stage"] == "before_start"
    cancelled = await app_client.post(
        f"{WRK}/bookings/{job['assignment_id']}/cancel",
        json={"reason": "Bike broke down"},
        headers=worker.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    state = (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    ).json()
    assert state["status"] == "searching"
    assert state["refunds"] == []
    assert state["arrival_code"] is None
    strikes = await db.fetchval(
        "SELECT count(*) FROM worker_strikes WHERE assignment_id = $1", UUID(job["assignment_id"])
    )
    assert strikes == (1 if preview["strike_weight"] > 0 else 0)


async def _worked(db: asyncpg.Connection, assignment_id: str, minutes: int) -> None:
    await db.execute(
        "UPDATE attendance_records SET checked_in_at = $2 WHERE assignment_id = $1",
        UUID(assignment_id),
        datetime.now(UTC) - timedelta(minutes=minutes),
    )


async def test_worker_force_cancel_is_not_paid_and_refunds_in_full(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Walks Off")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _started(app_client, business, worker, lat, lng)
    await _worked(db, job["assignment_id"], 30)
    preview = (
        await app_client.get(
            f"{WRK}/bookings/{job['assignment_id']}/cancel-preview", headers=worker.headers
        )
    ).json()
    assert preview["stage"] == "during_work"
    assert preview["business_refund_minor"] == TOTAL
    assert preview["fee_minor"] == 0 and preview["business_voucher"] is True
    cancelled = await app_client.post(
        f"{WRK}/bookings/{job['assignment_id']}/cancel", json={}, headers=worker.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    state = (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    ).json()
    assert state["status"] == "completed"
    assert state["assignment"]["ended_reason"] == "worker_left"
    assert all(r["status"] == "processed" for r in state["refunds"])
    assert sum(r["amount_minor"] for r in state["refunds"]) == TOTAL
    assert state["final_invoice"]["total_minor"] == 0
    assert await _ledger(db, job["assignment_id"]) == {}
    assert cancelled.json()["earnings"]["final_net_minor"] is None
    voucher = await db.fetchval(
        "SELECT voucher_promo_id FROM cancellation_charges WHERE assignment_id = $1",
        UUID(job["assignment_id"]),
    )
    assert voucher is not None


async def test_business_force_cancel_pays_in_full_and_worker_gets_share(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Stopped Early")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _started(app_client, business, worker, lat, lng)
    seat_url = f"{BIZ}/{booking['booking_id']}/workers/{job['assignment_id']}"
    preview = (await app_client.get(f"{seat_url}/cancel-preview", headers=business.headers)).json()
    assert preview["stage"] == "during_work"
    assert preview["business_refund_minor"] == 0
    assert preview["business_retained_minor"] == TOTAL
    assert preview["worker_compensation_minor"] == BASE * 80 // 100
    cancelled = await app_client.post(
        f"{seat_url}/cancel", json={"expected_refund_minor": 0}, headers=business.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "completed"
    assert body["final_invoice"]["total_minor"] == TOTAL
    assert body["refunds"] == []
    ledger = await _ledger(db, job["assignment_id"])
    assert sum(ledger.values()) == BASE * 80 // 100
    worker_view = (
        await app_client.get(f"{WRK}/bookings/{job['assignment_id']}", headers=worker.headers)
    ).json()
    assert worker_view["earnings"]["final_net_minor"] == BASE * 80 // 100
    entries = (
        await app_client.get(f"{API}/worker/earnings/entries", headers=worker.headers)
    ).json()["items"]
    assert [(e["entry_type"], e["amount_minor"]) for e in entries] == [
        ("shift_earning", BASE * 80 // 100)
    ]


async def test_business_end_without_code_is_a_force_cancel(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Ends Early")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _started(app_client, business, worker, lat, lng)
    whole = (
        await app_client.get(
            f"{BIZ}/{booking['booking_id']}/cancel-preview", headers=business.headers
        )
    ).json()
    assert whole["stage"] == "during_work" and whole["business_refund_minor"] == 0
    ended = await app_client.post(f"{BIZ}/{booking['booking_id']}/end", headers=business.headers)
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "completed"
    assert ended.json()["final_invoice"]["total_minor"] == TOTAL
    assert ended.json()["refunds"] == []
    assert sum((await _ledger(db, job["assignment_id"])).values()) == BASE * 80 // 100


async def test_completing_early_with_the_code_bills_worked_time(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Done Early")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _started(app_client, business, worker, lat, lng)
    await _worked(db, job["assignment_id"], 60)
    code = await live_completion_code(app_client, business, booking["booking_id"])
    done = await app_client.post(
        f"{WRK}/bookings/{job['assignment_id']}/complete",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert done.status_code == 200, done.text
    state = (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    ).json()
    half = TOTAL // 2
    assert state["final_invoice"]["total_minor"] == half
    assert [(r["amount_minor"], r["status"]) for r in state["refunds"]] == [
        (TOTAL - half, "processed")
    ]
    assert await _ledger(db, job["assignment_id"]) == {
        "shift_earning": BASE // 2,
        "commission": -(COMMISSION // 2),
    }
    assert done.json()["earnings"]["final_net_minor"] == (BASE - COMMISSION) // 2


# --- sweeps --------------------------------------------------------------------------


async def test_no_worker_found_refunds_in_full(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    lat, lng = _location()
    booking = await _searching(app_client, business, lat, lng)
    assert booking["search"]["notified_workers"] == 0
    await db.execute(
        "UPDATE shifts SET search_expires_at = now() - interval '1 second' WHERE id = $1",
        UUID(booking["booking_id"]),
    )
    await run_sweep_once(get_pool())
    state = (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    ).json()
    assert state["status"] == "no_workers"
    assert [(r["amount_minor"], r["status"]) for r in state["refunds"]] == [(TOTAL, "processed")]
    assert state["actions"]["can_repost"] is True


async def test_unpaid_booking_is_cancelled_after_payment_window(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    booking = await _posted(app_client, business, lat, lng)
    await db.execute(
        "UPDATE shifts SET published_at = now() - interval '2 hours' WHERE id = $1",
        UUID(booking["booking_id"]),
    )
    await run_sweep_once(get_pool())
    state = (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    ).json()
    assert state["status"] == "cancelled"
    assert state["cancellation"]["cancelled_by"] == "system"
    assert state["deposit_invoice"]["status"] == "void"


async def test_confirming_a_payment_twice_settles_once(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    lat, lng = _location()
    booking = await _posted(app_client, business, lat, lng)
    payment = await _pay(app_client, business, booking["deposit_invoice"]["id"])
    again = await app_client.post(
        f"{API}/business/payments/{payment['id']}/confirm", headers=business.headers
    )
    assert again.status_code == 200 and again.json()["status"] == "succeeded"
    histories = await db.fetchval(
        "SELECT count(*) FROM shift_status_history WHERE shift_id = $1 AND to_status = 'searching'",
        UUID(booking["booking_id"]),
    )
    assert histories == 1


# --- access control -------------------------------------------------------------------


async def test_other_parties_cannot_see_or_act(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker
) -> None:
    owner, stranger = await make_business(), await make_business("Other Cafe")
    worker, outsider = await make_worker("Assigned"), await make_worker("Outsider")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat, lng)
    booking, job = await _accepted(app_client, owner, worker, lat, lng)
    assert (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=stranger.headers)
    ).status_code == 404
    assert (
        await app_client.get(f"{WRK}/bookings/{job['assignment_id']}", headers=outsider.headers)
    ).status_code == 404
    assert (
        await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=worker.headers)
    ).status_code == 403
    assert (await app_client.get(f"{ADM}/pricing", headers=owner.headers)).status_code == 403


# --- admin (last: changes the active pricing, restored at the end) --------------------


async def test_admin_pricing_settings_audit_and_snapshots(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    admin = await _admin(app_client, db)
    business = await make_business()
    lat, lng = _location()
    old = await _posted(app_client, business, lat, lng)

    current = (await app_client.get(f"{ADM}/pricing", headers=admin.headers)).json()
    assert (current["commission_pct"], current["tax_pct"], current["extension_surcharge_pct"]) == (
        4.0,
        2.0,
        30.0,
    )
    assert current["example"]["total_minor"] == TOTAL

    defaults = {
        "commission_pct": "4",
        "tax_pct": "2",
        "tax_label": "Tax",
        "tax_base": "subtotal",
        "extension_surcharge_pct": "30",
    }
    for bad in (
        {"commission_pct": "101"},
        {"tax_pct": "-1"},
        {"commission_pct": "abc"},
        {"extension_surcharge_pct": "1.234"},
    ):
        resp = await app_client.put(
            f"{ADM}/pricing", json={**defaults, **bad}, headers=admin.headers
        )
        assert resp.status_code == 400, resp.text
        assert set(resp.json()["details"]["fields"]) == set(bad)

    try:
        updated = await app_client.put(
            f"{ADM}/pricing",
            json={
                **defaults,
                "commission_pct": "5",
                "tax_pct": "3",
                "tax_base": "commission",
                "tax_label": "Service tax",
                "notes": "Pilot pricing",
            },
            headers=admin.headers,
        )
        assert updated.status_code == 200, updated.text
        new = updated.json()
        assert new["version"] == current["version"] + 1
        assert new["example"]["commission_minor"] == 5000
        assert new["example"]["tax_minor"] == 150  # 3% of the 5,000 commission
        assert new["example"]["total_minor"] == 105150

        audit = (await app_client.get(f"{ADM}/pricing/audit", headers=admin.headers)).json()
        fields = {a["field"]: a for a in audit["items"] if a["settings_version"] == new["version"]}
        assert set(fields) == {"commission_pct", "tax_pct", "tax_base", "tax_label"}
        assert (fields["commission_pct"]["old_value"], fields["commission_pct"]["new_value"]) == (
            "4.00",
            "5.00",
        )
        assert fields["commission_pct"]["changed_by_user_id"] == str(admin.user_id)

        fresh = await app_client.post(
            BIZ,
            json=_create_body(lat, lng, expected_total_minor=105150),
            headers=business.headers,
        )
        assert fresh.status_code == 201, fresh.text
        assert fresh.json()["pricing"]["tax_label"] == "Service tax"
        assert fresh.json()["deposit_invoice"]["total_minor"] == 105150
        unchanged = (
            await app_client.get(f"{BIZ}/{old['booking_id']}", headers=business.headers)
        ).json()
        assert unchanged["pricing"]["total_minor"] == TOTAL
        assert unchanged["pricing"]["commission_pct"] == 4.0

        listing = (await app_client.get(f"{ADM}/bookings", headers=admin.headers)).json()
        assert listing["total"] >= 2
        detail = (
            await app_client.get(f"{ADM}/bookings/{old['booking_id']}", headers=admin.headers)
        ).json()
        assert "arrival_code" not in detail and "location" not in str(detail.keys())
        refunds = await app_client.get(f"{ADM}/refunds", headers=admin.headers)
        assert refunds.status_code == 200
    finally:
        restored = await app_client.put(f"{ADM}/pricing", json=defaults, headers=admin.headers)
        assert restored.status_code == 200, restored.text
