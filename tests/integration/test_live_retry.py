"""Live Work search retries: nobody accepted → add ₹10/₹20/₹30 to the pay and search again (up to
3 searches, one upfront payment, the extra billed at the end) or take a full refund."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from app.services.background.background_sweep_loop import run_sweep_once
from tests.integration.conftest import Actor, live_completion_code
from tests.integration.test_admin_crud import _admin
from tests.integration.test_live_work import (
    ADM,
    BIZ,
    MINUTES,
    RATE,
    TOTAL,
    WRK,
    _location,
    _pay,
    _place_worker,
    _searching,
    _worked,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _time_out(
    client: httpx.AsyncClient, business: Actor, db: asyncpg.Connection, booking_id: str
) -> dict:
    await db.execute(
        "UPDATE shifts SET search_expires_at = now() - interval '1 second' WHERE id = $1",
        UUID(booking_id),
    )
    await run_sweep_once(get_pool())
    state = await client.get(f"{BIZ}/{booking_id}", headers=business.headers)
    assert state.status_code == 200, state.text
    return state.json()


async def _retry(
    client: httpx.AsyncClient, business: Actor, booking_id: str, boost: int
) -> httpx.Response:
    return await client.post(
        f"{BIZ}/{booking_id}/retry", json={"boost_minor": boost}, headers=business.headers
    )


async def test_timeout_offers_a_retry_and_the_extra_pay_is_billed_at_the_end(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    booking = await _searching(app_client, business, lat, lng)
    booking_id = booking["booking_id"]

    state = await _time_out(app_client, business, db, booking_id)
    assert state["status"] == "no_workers"
    assert state["refunds"] == []
    retry = state["retry"]
    assert retry["search_round"] == 1 and retry["max_search_rounds"] == 3
    assert retry["boost_options_minor"] == [1000, 2000, 3000]
    assert 0 < retry["seconds_left"] <= 600
    assert state["actions"]["can_retry"] is True
    assert state["actions"]["can_cancel"] is True
    assert state["actions"]["can_repost"] is False
    active = await app_client.get(BIZ, params={"active": True}, headers=business.headers)
    assert booking_id in [b["booking_id"] for b in active.json()["items"]]

    bad = await _retry(app_client, business, booking_id, 1500)
    assert bad.status_code == 400, bad.text

    worker = await make_worker("Boosted Pay")
    await _place_worker(app_client, worker, lat, lng)
    retried = await _retry(app_client, business, booking_id, 2000)
    assert retried.status_code == 200, retried.text
    body = retried.json()
    assert body["status"] == "searching"
    assert body["retry"] is None and body["boost_minor"] == 2000
    assert body["search"]["notified_workers"] == 1
    again = await _retry(app_client, business, booking_id, 1000)
    assert again.status_code == 409, again.text

    boosted_base = (RATE + 2000) * MINUTES // 60
    requests = (await app_client.get(f"{WRK}/requests", headers=worker.headers)).json()
    offer = next(r for r in requests if r["booking_id"] == booking_id)
    assert offer["worker_net_minor"] == boosted_base - boosted_base * 4 // 100

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
    await _worked(db, assignment_id, MINUTES + 1)
    code = await live_completion_code(app_client, business, booking_id)
    done = await app_client.post(
        f"{WRK}/bookings/{assignment_id}/complete",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert done.status_code == 200, done.text

    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    final = state["final_invoice"]
    assert final["total_minor"] > TOTAL
    assert final["amount_due_minor"] == final["total_minor"] - TOTAL
    assert final["status"] != "paid"
    assert state["refunds"] == []

    await _pay(app_client, business, final["id"])
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["final_invoice"]["status"] == "paid"
    worker_view = (
        await app_client.get(f"{WRK}/bookings/{assignment_id}", headers=worker.headers)
    ).json()
    assert worker_view["earnings"]["final_net_minor"] == boosted_base - boosted_base * 4 // 100


async def test_three_searches_then_no_worker_nearby_refund(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    booking_id = (await _searching(app_client, business, lat, lng))["booking_id"]

    for round_no, boost in ((1, 1000), (2, 3000)):
        state = await _time_out(app_client, business, db, booking_id)
        assert state["retry"]["search_round"] == round_no
        assert (await _retry(app_client, business, booking_id, boost)).status_code == 200

    state = await _time_out(app_client, business, db, booking_id)
    assert state["status"] == "no_workers"
    assert state["retry"] is None
    assert state["boost_minor"] == 4000
    assert [(r["amount_minor"], r["status"]) for r in state["refunds"]] == [(TOTAL, "processed")]
    assert state["actions"]["can_repost"] is True
    late = await _retry(app_client, business, booking_id, 1000)
    assert late.status_code == 409, late.text
    notice = await db.fetchval(
        "SELECT title FROM notifications WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
        business.user_id,
    )
    assert notice == "No Worker nearby"


async def test_no_choice_within_ten_minutes_refunds(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    booking_id = (await _searching(app_client, business, lat, lng))["booking_id"]
    assert (await _time_out(app_client, business, db, booking_id))["retry"] is not None

    await db.execute(
        "UPDATE live_booking_pricing SET retry_offer_expires_at = now() - interval '1 second' "
        "WHERE shift_id = $1",
        UUID(booking_id),
    )
    await run_sweep_once(get_pool())
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert state["retry"] is None
    assert [(r["amount_minor"], r["status"]) for r in state["refunds"]] == [(TOTAL, "processed")]
    assert (await _retry(app_client, business, booking_id, 1000)).status_code == 409
    await run_sweep_once(get_pool())
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert len(state["refunds"]) == 1


async def test_get_refund_instead_of_retrying(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    lat, lng = _location()
    booking_id = (await _searching(app_client, business, lat, lng))["booking_id"]
    await _time_out(app_client, business, db, booking_id)

    preview = await app_client.get(f"{BIZ}/{booking_id}/cancel-preview", headers=business.headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["stage"] == "before_acceptance"
    assert preview.json()["business_refund_minor"] == TOTAL
    cancelled = await app_client.post(
        f"{BIZ}/{booking_id}/cancel",
        json={"expected_refund_minor": TOTAL},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "cancelled" and body["retry"] is None
    assert [(r["amount_minor"], r["status"]) for r in body["refunds"]] == [(TOTAL, "processed")]
    await run_sweep_once(get_pool())
    state = (await app_client.get(f"{BIZ}/{booking_id}", headers=business.headers)).json()
    assert len(state["refunds"]) == 1


async def test_admin_changes_search_rules_for_new_bookings_only(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    admin = await _admin(app_client, db)
    business = await make_business()
    lat, lng = _location()
    old_id = (await _searching(app_client, business, lat, lng))["booking_id"]

    current = (await app_client.get(f"{ADM}/pricing", headers=admin.headers)).json()
    assert (
        current["search_timeout_minutes"],
        current["max_search_rounds"],
        current["retry_choice_minutes"],
        current["boost_options_minor"],
    ) == (30, 3, 10, [1000, 2000, 3000])
    rates = {
        "commission_pct": "4",
        "tax_pct": "2",
        "tax_label": "Tax",
        "tax_base": "subtotal",
        "extension_surcharge_pct": "30",
    }
    for bad in (
        {"search_timeout_minutes": 2},
        {"max_search_rounds": 9},
        {"retry_choice_minutes": 0},
        {"boost_options_minor": []},
        {"boost_options_minor": [1050]},
        {"boost_options_minor": [1000, 1000]},
    ):
        resp = await app_client.put(f"{ADM}/pricing", json={**rates, **bad}, headers=admin.headers)
        assert resp.status_code == 400, resp.text
        assert set(resp.json()["details"]["fields"]) == set(bad)

    try:
        updated = await app_client.put(
            f"{ADM}/pricing",
            json={
                **rates,
                "search_timeout_minutes": 15,
                "max_search_rounds": 2,
                "retry_choice_minutes": 5,
                "boost_options_minor": [5000, 1500],
            },
            headers=admin.headers,
        )
        assert updated.status_code == 200, updated.text
        new = updated.json()
        assert new["version"] == current["version"] + 1
        assert new["boost_options_minor"] == [1500, 5000]
        audit = (await app_client.get(f"{ADM}/pricing/audit", headers=admin.headers)).json()
        fields = {a["field"]: a for a in audit["items"] if a["settings_version"] == new["version"]}
        assert set(fields) == {
            "search_timeout_minutes",
            "max_search_rounds",
            "retry_choice_minutes",
            "boost_options_minor",
        }
        assert fields["boost_options_minor"]["new_value"] == "1500,5000"

        fresh = await _searching(app_client, business, *_location())
        left = (
            datetime.fromisoformat(fresh["search"]["expires_at"]) - datetime.now(UTC)
        ).total_seconds()
        assert 14 * 60 < left <= 15 * 60
        state = await _time_out(app_client, business, db, fresh["booking_id"])
        assert state["retry"]["max_search_rounds"] == 2
        assert state["retry"]["boost_options_minor"] == [1500, 5000]
        assert 4 * 60 < state["retry"]["seconds_left"] <= 5 * 60
        assert (await _retry(app_client, business, fresh["booking_id"], 1000)).status_code == 400
        assert (await _retry(app_client, business, fresh["booking_id"], 1500)).status_code == 200
        state = await _time_out(app_client, business, db, fresh["booking_id"])
        assert state["retry"] is None
        assert [r["amount_minor"] for r in state["refunds"]] == [TOTAL]

        # The booking made before the change keeps its own rules.
        old = await _time_out(app_client, business, db, old_id)
        assert old["retry"]["max_search_rounds"] == 3
        assert old["retry"]["boost_options_minor"] == [1000, 2000, 3000]
    finally:
        restored = await app_client.put(
            f"{ADM}/pricing",
            json={
                **rates,
                "search_timeout_minutes": 30,
                "max_search_rounds": 3,
                "retry_choice_minutes": 10,
                "boost_options_minor": [1000, 2000, 3000],
            },
            headers=admin.headers,
        )
        assert restored.status_code == 200, restored.text
