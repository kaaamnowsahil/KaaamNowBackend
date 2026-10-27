"""Cancellation fees, compensation, strikes, vouchers and unfilled seats (rules §5, §6, §9).

Every shift here: ₹120/h × 4h30m = ₹540 booking per seat. Business pays 540 + 4% (21.60)
+ 2% gateway on 561.60 (11.23) = ₹572.83 per seat at posting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx

from app.db.pool import get_pool
from app.services.shifts.shift_sweeps import release_unfilled_seats
from tests.integration.conftest import pay_deposit

API = "/api/v1"
BOOKING = 54000
COMMISSION = 2160  # 4% of BOOKING
GATEWAY = 1123  # 2% of BOOKING + COMMISSION
TAX = 1123  # default 2% tax on BOOKING + COMMISSION (tax base "subtotal")
SEAT_TOTAL = BOOKING + COMMISSION + GATEWAY + TAX


async def _booked_shift(  # type: ignore[no-untyped-def]
    client: httpx.AsyncClient,
    db: asyncpg.Connection,
    business,
    workers,
    *,
    starts_in: timedelta,
    seats: int = 1,
) -> tuple[str, list[str]]:
    """Posts + pays 2 days out, books ``workers``, then moves the start to ``now + starts_in``."""
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    resp = await client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "Cancellation test",
            "workers_required": seats,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 300,
            "break_minutes": 30,
            "publish": True,
        },
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    shift_id = resp.json()["id"]
    await pay_deposit(client, business, shift_id)
    assignment_ids = []
    for worker in workers:
        applied = await client.post(
            f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
        )
        assert applied.status_code == 201, applied.text
        my = (await client.get(f"{API}/worker/my-shifts", headers=worker.headers)).json()
        assignment_ids.append(
            next(i["assignment_id"] for i in my["items"] if i["shift"]["id"] == shift_id)
        )
    new_start = datetime.now(UTC) + starts_in
    await db.execute(
        "UPDATE shifts SET starts_at = $2, ends_at = $3 WHERE id = $1",
        UUID(shift_id),
        new_start,
        new_start + timedelta(minutes=300),
    )
    return shift_id, assignment_ids


async def _balance(client: httpx.AsyncClient, worker) -> int:  # type: ignore[no-untyped-def]
    summary = await client.get(f"{API}/worker/earnings", headers=worker.headers)
    return summary.json()["available_minor"]


async def _vouchers(db: asyncpg.Connection, business) -> int:  # type: ignore[no-untyped-def]
    return await db.fetchval(
        "SELECT count(*) FROM promo_codes WHERE owner_user_id = $1 AND source = 'system'",
        business.user_id,
    )


async def test_worker_cancel_fee_tiers_strike_and_voucher(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Tier Worker", online=False)

    _, (early,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(hours=5)
    )
    preview = await app_client.get(
        f"{API}/worker/assignments/{early}/cancel-preview", headers=worker.headers
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["fee_minor"] == 8900
    assert preview.json()["seat_reopens"] is True
    cancelled = await app_client.post(
        f"{API}/worker/assignments/{early}/cancel",
        json={"reason": "Fell sick"},
        headers=worker.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["charge"]["fee_minor"] == 8900
    assert cancelled.json()["shift_status"] == "open"
    assert await _balance(app_client, worker) == -8900
    assert await _vouchers(db, business) == 0

    _, (late,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(hours=1)
    )
    cancelled = await app_client.post(
        f"{API}/worker/assignments/{late}/cancel",
        json={"reason": "Bus broke down"},
        headers=worker.headers,
    )
    charge = cancelled.json()["charge"]
    assert charge["fee_minor"] == 14900
    assert charge["strike_weight"] == 0.5
    assert charge["business_voucher"] is True
    assert charge["business_refund_minor"] == SEAT_TOTAL
    assert cancelled.json()["shift_status"] == "filled"
    assert await _balance(app_client, worker) == -8900 - 14900
    assert await _vouchers(db, business) == 1


async def test_business_cancel_pays_fee_and_compensates_worker(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Comp Worker", online=False)
    shift_id, _ = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(hours=4)
    )
    fee = BOOKING * 70 // 100
    # Commission and tax are kept on the fee's share (70%); the gateway charge is kept.
    retained = fee + 1512 + 786 + GATEWAY
    preview = (
        await app_client.get(
            f"{API}/business/shifts/{shift_id}/cancel-preview", headers=business.headers
        )
    ).json()
    assert preview["fee_minor"] == fee
    assert preview["worker_compensation_minor"] == BOOKING * 40 // 100
    assert preview["business_refund_minor"] == SEAT_TOTAL - retained

    cancelled = await app_client.post(
        f"{API}/business/shifts/{shift_id}/cancel",
        json={"reason": "Plan changed"},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    deposit = (
        await app_client.get(
            f"{API}/business/invoices/{cancelled.json()['deposit_invoice_id']}",
            headers=business.headers,
        )
    ).json()
    assert deposit["refund_due_minor"] == SEAT_TOTAL - retained
    assert await _balance(app_client, worker) == BOOKING * 40 // 100


async def test_free_business_cancel_keeps_only_gateway(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Free Worker", online=False)
    shift_id, _ = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(hours=30)
    )
    preview = (
        await app_client.get(
            f"{API}/business/shifts/{shift_id}/cancel-preview", headers=business.headers
        )
    ).json()
    assert preview["fee_minor"] == 0
    assert preview["business_refund_minor"] == SEAT_TOTAL - GATEWAY


async def test_no_show_fee_strikes_and_ban(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("No Show Worker", online=False)
    _, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(hours=-1)
    )
    await db.execute(
        "INSERT INTO worker_strikes (worker_profile_id, weight, reason, expires_at) "
        "VALUES ($1, 2.5, 'seed', now() + interval '30 days')",
        worker.profile_id,
    )
    marked = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/no-show", headers=business.headers
    )
    assert marked.status_code == 200, marked.text
    assert await _balance(app_client, worker) == -(BOOKING // 2)
    assert await _vouchers(db, business) == 1
    banned_at = await db.fetchval(
        "SELECT banned_at FROM worker_profiles WHERE id = $1", worker.profile_id
    )
    assert banned_at is not None

    starts = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
    other = await app_client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "After ban",
            "workers_required": 1,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 300,
            "publish": True,
        },
        headers=business.headers,
    )
    await pay_deposit(app_client, business, other.json()["id"])
    blocked = await app_client.post(
        f"{API}/worker/shifts/{other.json()['id']}/applications", json={}, headers=worker.headers
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["code"] == "worker_banned"


async def test_unfilled_seats_released_at_apply_cutoff(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Only Worker", online=False)
    shift_id, _ = await _booked_shift(
        app_client, db, business, [worker], starts_in=timedelta(minutes=90), seats=2
    )
    assert await release_unfilled_seats(get_pool()) >= 1
    status = await db.fetchval("SELECT status FROM shifts WHERE id = $1", UUID(shift_id))
    assert status == "filled"
    refund = await db.fetchval(
        "SELECT business_refund_minor FROM cancellation_charges "
        "WHERE shift_id = $1 AND event = 'unfilled'",
        UUID(shift_id),
    )
    assert refund == SEAT_TOTAL
    assert await _vouchers(db, business) == 1
