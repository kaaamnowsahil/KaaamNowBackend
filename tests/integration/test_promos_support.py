"""Promo codes (business at posting, worker on next payout), emergency tickets and admin
booking overrides. Booking: ₹120/h × 4h30m = ₹540; commission ₹21.60, gateway ₹11.23."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import httpx

from tests.integration.conftest import login, next_phone
from tests.integration.test_cancellations import BOOKING, _balance, _booked_shift
from tests.integration.test_day_of_shift import _check_in

API = "/api/v1"
COMMISSION = 2160
GATEWAY = 1123
# 2% tax on the subtotal after the half-commission coupon: (54000 + 1080) × 2% = 1101.6 → 1102.
DISCOUNTED_TAX = 1102


async def _promo(db: asyncpg.Connection, code: str, role: str, **fields) -> None:  # type: ignore[no-untyped-def]
    values = {
        "discount_type": "percent",
        "discount_value": 50,
        "applies_to": "commission",
        **fields,
    }
    await db.execute(
        "INSERT INTO promo_codes (code, target_role, discount_type, discount_value, applies_to)"
        " VALUES ($1, $2, $3, $4, $5)",
        code,
        role,
        values["discount_type"],
        values["discount_value"],
        values["applies_to"],
    )


def _shift_body(promo_code: str | None) -> dict:
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    return {
        "shift_type": "scheduled",
        "category_slug": "house-help",
        "job_title": "Promo test",
        "workers_required": 1,
        "hourly_rate_minor": 12000,
        "starts_at": starts.isoformat(),
        "duration_minutes": 300,
        "break_minutes": 30,
        "publish": True,
        "promo_code": promo_code,
    }


async def _admin(client: httpx.AsyncClient, db: asyncpg.Connection):  # type: ignore[no-untyped-def]
    phone = next_phone()
    user_id = await db.fetchval("INSERT INTO users (phone) VALUES ($1) RETURNING id", phone)
    await db.execute(
        "INSERT INTO user_roles (user_id, role, status) VALUES ($1, 'admin', 'active')", user_id
    )
    return await login(client, phone)


async def test_business_promo_discounts_deposit_and_is_released_on_cancel(  # type: ignore[no-untyped-def]
    app_client, db, make_business
) -> None:
    business = await make_business()
    await _promo(db, "half50", "business")

    bad = await app_client.post(
        f"{API}/business/promo-codes/validate", json={"code": "NOPE"}, headers=business.headers
    )
    assert bad.status_code == 400 and bad.json()["details"]["reason"] == "not_found"
    estimate = await app_client.post(
        f"{API}/business/shifts/estimate",
        json={
            "hourly_rate_minor": 12000,
            "workers_required": 1,
            "duration_minutes": 300,
            "break_minutes": 30,
            "promo_code": "HALF50",
        },
        headers=business.headers,
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["promo_discount_minor"] == COMMISSION // 2
    assert estimate.json()["total_minor"] == BOOKING + COMMISSION // 2 + GATEWAY + DISCOUNTED_TAX

    posted = await app_client.post(
        f"{API}/business/shifts", json=_shift_body("Half50"), headers=business.headers
    )
    assert posted.status_code == 201, posted.text
    deposit = (
        await app_client.get(
            f"{API}/business/invoices/{posted.json()['deposit_invoice_id']}",
            headers=business.headers,
        )
    ).json()
    assert deposit["promo_code"] == "half50"
    assert deposit["promo_discount_minor"] == COMMISSION // 2
    assert deposit["total_minor"] == BOOKING + COMMISSION // 2 + GATEWAY + DISCOUNTED_TAX

    again = await app_client.post(
        f"{API}/business/shifts", json=_shift_body("HALF50"), headers=business.headers
    )
    assert again.status_code == 400 and again.json()["details"]["reason"] == "already_used"

    cancelled = await app_client.post(
        f"{API}/business/shifts/{posted.json()['id']}/cancel",
        json={"reason": "Plans changed"},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert await db.fetchval("SELECT used_count FROM promo_codes WHERE code = 'half50'") == 0
    usable = await app_client.post(
        f"{API}/business/promo-codes/validate", json={"code": "half50"}, headers=business.headers
    )
    assert usable.status_code == 200, usable.text


async def test_worker_promo_discounts_next_payout_commission(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Promo Worker", online=False)
    await _promo(db, "WFREE", "worker", discount_value=100)
    await _promo(db, "WFREE2", "worker", discount_value=100)
    wrong_role = await app_client.post(
        f"{API}/business/promo-codes/validate", json={"code": "WFREE"}, headers=business.headers
    )
    assert wrong_role.json()["details"]["reason"] == "wrong_role"

    redeemed = await app_client.post(
        f"{API}/worker/promo-codes/redeem", json={"code": "wfree"}, headers=worker.headers
    )
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["pending"]["code"] == "WFREE"
    second = await app_client.post(
        f"{API}/worker/promo-codes/redeem", json={"code": "WFREE2"}, headers=worker.headers
    )
    assert second.status_code == 409, second.text

    shift_id, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=-timedelta(minutes=60)
    )
    await _check_in(app_client, business, worker, assignment_id)
    stopped = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/stop",
        json={"reason": "business_stopped"},
        headers=business.headers,
    )
    assert stopped.status_code == 200, stopped.text
    invoice = await app_client.post(
        f"{API}/business/shifts/{shift_id}/invoice", headers=business.headers
    )
    assert invoice.json()["status"] == "paid", invoice.text
    # 80% of booking, plus the whole 4% commission back from the promo.
    assert await _balance(app_client, worker) == BOOKING * 80 // 100 + COMMISSION
    status = await app_client.get(f"{API}/worker/promo-codes", headers=worker.headers)
    assert status.json()["pending"] is None


async def test_emergency_ticket_and_admin_overrides(  # type: ignore[no-untyped-def]
    app_client, db, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Emergency Worker", online=False)
    admin = await _admin(app_client, db)
    _, (assignment_id,) = await _booked_shift(
        app_client, db, business, [worker], starts_in=-timedelta(minutes=60)
    )
    await _check_in(app_client, business, worker, assignment_id)

    stranger = await make_business("Someone Else")
    hidden = await app_client.post(
        f"{API}/support/emergency",
        json={"assignment_id": assignment_id},
        headers=stranger.headers,
    )
    assert hidden.status_code == 404, hidden.text
    ticket = await app_client.post(
        f"{API}/support/emergency",
        json={"assignment_id": assignment_id, "message": "Worker left mid-shift"},
        headers=business.headers,
    )
    assert ticket.status_code == 201, ticket.text
    assert ticket.json()["priority"] == "urgent"
    assert await db.fetchval(
        "SELECT count(*) FROM notifications WHERE user_id = $1 AND kind = 'support_emergency'",
        admin.user_id,
    )

    left = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/stop",
        json={"reason": "worker_left"},
        headers=business.headers,
    )
    assert left.status_code == 200, left.text
    assert await _balance(app_client, worker) == -BOOKING // 2

    forbidden = await app_client.post(
        f"{API}/admin/bookings/{assignment_id}/overrides",
        json={"action": "waive_worker_fee", "reason": "Worker had a family emergency"},
        headers=business.headers,
    )
    assert forbidden.status_code == 403, forbidden.text
    waived = await app_client.post(
        f"{API}/admin/bookings/{assignment_id}/overrides",
        json={
            "action": "waive_worker_fee",
            "reason": "Worker had a family emergency",
            "support_ticket_id": ticket.json()["id"],
        },
        headers=admin.headers,
    )
    assert waived.status_code == 201, waived.text
    assert waived.json()["amount_minor"] == BOOKING // 2
    assert await _balance(app_client, worker) == 0
    twice = await app_client.post(
        f"{API}/admin/bookings/{assignment_id}/overrides",
        json={"action": "waive_worker_fee", "reason": "Worker had a family emergency"},
        headers=admin.headers,
    )
    assert twice.status_code == 409, twice.text

    revoked = await app_client.post(
        f"{API}/admin/bookings/{assignment_id}/overrides",
        json={"action": "revoke_voucher", "reason": "Business caused the walk-off"},
        headers=admin.headers,
    )
    assert revoked.status_code == 201, revoked.text
    no_strike = await app_client.post(
        f"{API}/admin/bookings/{assignment_id}/overrides",
        json={"action": "void_strike", "reason": "Walk-off carries no strike"},
        headers=admin.headers,
    )
    assert no_strike.status_code == 409, no_strike.text
    refund = await app_client.post(
        f"{API}/admin/bookings/{assignment_id}/overrides",
        json={"action": "refund_business", "reason": "Goodwill refund", "amount_minor": 5000},
        headers=admin.headers,
    )
    assert refund.status_code == 201, refund.text

    ledger = await app_client.get(
        f"{API}/admin/bookings/{assignment_id}/ledger", headers=admin.headers
    )
    assert ledger.status_code == 200, ledger.text
    body = ledger.json()
    assert {e["kind"] for e in body["worker_entries"]} >= {"cancellation_fee", "fee_waiver"}
    assert body["vouchers"][0]["kind"] == "voucher_inactive"
    assert [o["action"] for o in body["overrides"]] == [
        "refund_business",
        "revoke_voucher",
        "waive_worker_fee",
    ]
