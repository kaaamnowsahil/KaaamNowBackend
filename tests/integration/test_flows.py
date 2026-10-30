"""End-to-end Figma flows against a real database."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.services.billing.validation.webhook_signature import sign_payload
from app.services.earnings.earnings_sweeps import advance_processing_withdrawals
from app.services.users.deletion_service import process_deletion_requests
from tests.integration.conftest import NEAR_LAT, NEAR_LNG, completion_code, login, pay_deposit

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"


async def _live_shift(client: httpx.AsyncClient, business, workers_required: int = 1) -> dict:  # type: ignore[no-untyped-def]
    resp = await client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "live",
            "category_slug": "hospitality",
            "job_title": "Barista",
            "workers_required": workers_required,
            "hourly_rate_minor": 15000,
            "duration_minutes": 240,
            "publish": True,
        },
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _work_and_pay(client, db, business, worker, shift, assignment_id) -> dict:  # type: ignore[no-untyped-def]
    """Check in, check out, approve 3 h, invoice, pay; returns the receipt."""
    resp = await client.post(
        f"{API}/worker/assignments/{assignment_id}/check-in",
        json={"latitude": 28.6316, "longitude": 77.2168, "check_in_code": "0000"},
        headers=worker.headers,
    )
    assert resp.status_code == 400, resp.text
    resp = await client.post(
        f"{API}/worker/assignments/{assignment_id}/check-in",
        json={
            "latitude": 28.6316,
            "longitude": 77.2168,
            "check_in_code": shift["check_in_code"],
        },
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text
    code = await completion_code(client, business, assignment_id)
    resp = await client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out",
        json={"completion_code": code},
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{API}/business/assignments/{assignment_id}/attendance/approve",
        json={"approved_minutes": 180},
        headers=business.headers,
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"{API}/business/shifts/{shift['id']}/invoice", headers=business.headers
    )
    assert resp.status_code in (200, 201), resp.text
    invoice = resp.json()
    assert invoice["worker_subtotal_minor"] == 45000  # 3 h x Rs 150
    again = await client.post(
        f"{API}/business/shifts/{shift['id']}/invoice", headers=business.headers
    )
    assert again.json()["id"] == invoice["id"]

    resp = await client.post(
        f"{API}/business/invoices/{invoice['id']}/payments",
        json={"method": "upi_qr"},
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    payment = resp.json()
    assert payment["upi_payload"].startswith("upi://pay")
    resp = await client.post(
        f"{API}/business/payments/{payment['id']}/confirm", headers=business.headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "succeeded"
    receipt = await client.get(f"{API}/business/payments/{payment['id']}", headers=business.headers)
    assert receipt.status_code == 200, receipt.text
    return receipt.json()


async def test_public_catalog_and_content(app_client: httpx.AsyncClient) -> None:
    cats = (await app_client.get(f"{API}/work-categories")).json()
    slugs = {c["slug"] for c in (cats["items"] if isinstance(cats, dict) else cats)}
    assert {"house-help", "cooking", "driver", "other"} <= slugs
    terms = await app_client.get(f"{API}/content/terms", params={"audience": "worker"})
    assert terms.status_code == 200 and terms.json()["audience"] == "worker"
    faqs = await app_client.get(f"{API}/content/faqs", params={"audience": "business"})
    assert faqs.status_code == 200 and faqs.json()["support_email"]


async def test_auth_refresh_rotation_and_reuse(app_client: httpx.AsyncClient) -> None:
    phone = "+919811100001"
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO users (phone) VALUES ($1)", phone)
    await app_client.post(f"{API}/auth/otp/send", json={"phone": phone})
    bad = await app_client.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": "000000"})
    assert bad.status_code == 400
    tokens = (
        await app_client.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": "123456"})
    ).json()["tokens"]
    first = tokens["refresh_token"]
    rotated = await app_client.post(f"{API}/auth/token/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200, rotated.text
    racing = await app_client.post(f"{API}/auth/token/refresh", json={"refresh_token": first})
    assert racing.status_code == 200, racing.text  # concurrent retry within the grace window
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked_at = revoked_at - interval '1 hour' "
            "WHERE token_hash = encode(sha256($1::text::bytea), 'hex')",
            first,
        )
    reused = await app_client.post(f"{API}/auth/token/refresh", json={"refresh_token": first})
    assert reused.status_code == 401
    newer = rotated.json()["refresh_token"]
    revoked = await app_client.post(f"{API}/auth/token/refresh", json={"refresh_token": newer})
    assert revoked.status_code == 401  # whole family revoked after reuse


async def test_login_requires_existing_account(app_client: httpx.AsyncClient) -> None:
    phone = "+919811100099"
    sent = await app_client.post(f"{API}/auth/otp/send", json={"phone": phone, "intent": "sign_in"})
    assert sent.status_code == 404
    verified = await app_client.post(
        f"{API}/auth/otp/verify", json={"phone": phone, "code": "123456"}
    )
    assert verified.status_code == 400
    async with get_pool().acquire() as conn:
        assert await conn.fetchval("SELECT 1 FROM users WHERE phone = $1", phone) is None


async def test_rbac_and_ownership(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker()
    assert (
        await app_client.get(f"{API}/worker/earnings", headers=business.headers)
    ).status_code == 403
    assert (
        await app_client.get(f"{API}/business/dashboard", headers=worker.headers)
    ).status_code == 403
    shift = await _live_shift(app_client, business)
    other = await make_business("Other Cafe")
    resp = await app_client.get(f"{API}/business/shifts/{shift['id']}", headers=other.headers)
    assert resp.status_code == 404
    assert resp.json()["code"]
    await app_client.post(
        f"{API}/business/shifts/{shift['id']}/cancel", json={}, headers=business.headers
    )


async def test_account_deletion_request_review_holds_and_anonymization(
    app_client, make_business, make_worker, db
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    shift = await _live_shift(app_client, business)
    worker = await make_worker(online=False)

    anonymous = await app_client.post(f"{API}/me/deletion-requests")
    assert anonymous.status_code == 401
    requested = await app_client.post(f"{API}/me/deletion-requests", headers=business.headers)
    assert requested.status_code == 202, requested.text
    request = requested.json()
    assert request["status"] == "pending"
    assert "1 active shift" in request["blockers"]
    assert "1 pending verification review" in request["blockers"]
    assert await db.fetchval("SELECT is_active FROM users WHERE id = $1", business.user_id)

    # An approved request must be rechecked when the background processor runs.
    await db.execute(
        "UPDATE account_deletion_requests SET status = 'approved', approved_at = now() "
        "WHERE id = $1",
        request["id"],
    )
    assert await process_deletion_requests(get_pool()) == 0
    assert await db.fetchval("SELECT is_active FROM users WHERE id = $1", business.user_id)

    # The shift starts now, inside the 12 h Business cancellation cutoff; move it a day out so
    # the blocker can be cleared through the normal cancel endpoint.
    await db.execute(
        "UPDATE shifts SET starts_at = starts_at + interval '1 day', "
        "ends_at = ends_at + interval '1 day' WHERE id = $1",
        UUID(shift["id"]),
    )
    cancelled = await app_client.post(
        f"{API}/business/shifts/{shift['id']}/cancel",
        json={},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    await db.execute(
        "UPDATE business_profiles SET verification_status = 'verified' WHERE user_id = $1",
        business.user_id,
    )
    assert (
        await app_client.get(f"{API}/me/deletion-requests/current", headers=business.headers)
    ).json()["status"] == "approved"

    admin_phone = "+919099999999"
    await db.execute("INSERT INTO users (phone) VALUES ($1)", admin_phone)
    admin_id = await db.fetchval("SELECT id FROM users WHERE phone = $1", admin_phone)
    await db.execute(
        "INSERT INTO user_roles (user_id, role, status) VALUES ($1, 'admin', 'active')",
        admin_id,
    )
    admin = await login(app_client, admin_phone)
    hold = await app_client.post(
        f"{API}/admin/account-deletion-requests/{request['id']}/holds",
        json={
            "basis": "legal_obligation",
            "reason": "Retain this account data while the named review remains open.",
            "reference": "CASE-001",
            "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
        headers=admin.headers,
    )
    assert hold.status_code == 200, hold.text
    assert hold.json()["status"] == "on_hold"
    hold_id = hold.json()["holds"][0]["id"]
    released = await app_client.delete(
        f"{API}/admin/account-deletion-requests/{request['id']}/holds/{hold_id}",
        headers=admin.headers,
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "pending"
    approved = await app_client.post(
        f"{API}/admin/account-deletion-requests/{request['id']}/approve",
        headers=admin.headers,
    )
    assert approved.status_code == 200, approved.text

    assert await process_deletion_requests(get_pool()) == 1
    assert (
        await db.fetchval("SELECT is_active FROM users WHERE id = $1", business.user_id)
    ) is False
    assert await db.fetchval("SELECT count(*) FROM users WHERE id = $1", business.user_id) == 1
    assert (
        await db.fetchval(
            "SELECT count(*) FROM refresh_tokens WHERE user_id = $1 AND revoked_at IS NULL",
            business.user_id,
        )
    ) == 0
    assert (
        await db.fetchval(
            "SELECT count(*) FROM business_profiles WHERE id = $1",
            business.profile_id,
        )
    ) == 1
    assert (
        await db.fetchval(
            "SELECT count(*) FROM shifts WHERE business_profile_id = $1",
            business.profile_id,
        )
    ) == 1
    assert (
        await db.fetchval(
            "SELECT count(*) FROM shifts WHERE id::text = $1",
            shift["id"],
        )
    ) == 1
    stale_token = await app_client.get(f"{API}/me/profile", headers=business.headers)
    assert stale_token.status_code == 401
    assert stale_token.json()["code"] == "account_disabled"
    completed = await app_client.get(
        f"{API}/me/deletion-requests/current", headers=business.headers
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"]
    assert completed.json()["blockers"] == []
    assert (
        await db.fetchval("SELECT phone FROM users WHERE id = $1", business.user_id)
    ) != business.phone
    assert await db.fetchval("SELECT count(*) FROM shifts WHERE id = $1", shift["id"]) == 1

    worker_request = await app_client.post(f"{API}/me/deletion-requests", headers=worker.headers)
    assert worker_request.status_code == 202, worker_request.text
    assert worker_request.json()["blockers"] == []
    worker_approved = await app_client.post(
        f"{API}/admin/account-deletion-requests/{worker_request.json()['id']}/approve",
        headers=admin.headers,
    )
    assert worker_approved.status_code == 200, worker_approved.text
    assert await process_deletion_requests(get_pool()) == 1
    assert (await db.fetchval("SELECT is_active FROM users WHERE id = $1", worker.user_id)) is False
    assert (
        await db.fetchval("SELECT count(*) FROM worker_profiles WHERE id = $1", worker.profile_id)
        == 1
    )
    assert (
        await app_client.get(f"{API}/me/deletion-requests/current", headers=worker.headers)
    ).json()["status"] == "completed"


async def test_worker_feed_filters_by_business_type(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker("Business type filter worker")
    shift = await _live_shift(app_client, business)
    params = {"lat": NEAR_LAT, "lng": NEAR_LNG, "shift_type": "live"}

    matching = await app_client.get(
        f"{API}/worker/feed",
        params={**params, "business_type_slugs": "hospitality"},
        headers=worker.headers,
    )
    assert matching.status_code == 200, matching.text
    assert any(item["id"] == shift["id"] for item in matching.json()["items"])

    non_matching = await app_client.get(
        f"{API}/worker/feed",
        params={**params, "business_type_slugs": "hotel"},
        headers=worker.headers,
    )
    assert non_matching.status_code == 200, non_matching.text
    assert all(item["id"] != shift["id"] for item in non_matching.json()["items"])


async def test_live_flow_end_to_end(app_client, db, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker("Aarav")
    loser = await make_worker("Ravi")
    shift = await _live_shift(app_client, business)
    assert shift["status"] == "searching"

    requests = (await app_client.get(f"{API}/worker/live-requests", headers=worker.headers)).json()
    items = requests["items"] if isinstance(requests, dict) else requests
    assert any(
        str(r["shift"]["id"] if "shift" in r else r["shift_id"]) == shift["id"] for r in items
    )

    accepted = await app_client.post(
        f"{API}/worker/live-shifts/{shift['id']}/accept", headers=worker.headers
    )
    assert accepted.status_code == 200, accepted.text
    assignment_id = accepted.json()["id"]
    late = await app_client.post(
        f"{API}/worker/live-shifts/{shift['id']}/accept", headers=loser.headers
    )
    assert late.status_code in (404, 409), late.text

    detail = (
        await app_client.get(f"{API}/business/shifts/{shift['id']}", headers=business.headers)
    ).json()
    assert detail["status"] == "filled"

    msg = await app_client.post(
        f"{API}/assignments/{assignment_id}/messages",
        json={"body": "On my way"},
        headers=worker.headers,
    )
    assert msg.status_code == 201, msg.text
    thread = await app_client.get(
        f"{API}/assignments/{assignment_id}/messages", headers=business.headers
    )
    assert thread.status_code == 200

    early = await app_client.post(
        f"{API}/assignments/{assignment_id}/ratings", json={"stars": 5}, headers=business.headers
    )
    assert early.status_code == 409

    receipt = await _work_and_pay(app_client, db, business, worker, detail, assignment_id)
    assert receipt["invoice"]["status"] == "paid"

    summary = (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()
    assert summary["available_minor"] == 43200  # Rs 450 - 4% commission
    assert summary["lifetime_minor"] == 43200
    assert summary["completed_shifts"] == 1

    rate = await app_client.post(
        f"{API}/assignments/{assignment_id}/ratings",
        json={"stars": 5, "tags": ["bogus-tag"]},
        headers=business.headers,
    )
    assert rate.status_code == 400
    rate = await app_client.post(
        f"{API}/assignments/{assignment_id}/ratings",
        json={"stars": 4, "review": "Great work"},
        headers=business.headers,
    )
    assert rate.status_code == 201, rate.text
    dup = await app_client.post(
        f"{API}/assignments/{assignment_id}/ratings", json={"stars": 3}, headers=business.headers
    )
    assert dup.status_code == 409
    profile = (await app_client.get(f"{API}/me/profile", headers=worker.headers)).json()
    assert float(profile["worker"]["rating_avg"]) == 4.0
    notes = (await app_client.get(f"{API}/notifications", headers=worker.headers)).json()
    kinds = {n["kind"] for n in notes["items"]}
    assert {"earning_credited", "rating_received"} <= kinds


async def test_scheduled_flow(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker("Meena", online=False)
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    resp = await app_client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "House help for a party",
            "workers_required": 1,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 300,
            "break_minutes": 30,
            "publish": True,
        },
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    shift = resp.json()
    assert shift["status"] == "awaiting_payment"
    # Rs 540 + 4% + 2% gateway + 2% tax on Rs 561.60
    assert shift["estimate"]["total_minor"] == 58406
    assert shift["estimate"]["tax_minor"] == 1123
    assert shift["estimate"]["tax_base"] == "subtotal"
    shift = await pay_deposit(app_client, business, shift["id"])

    feed = (
        await app_client.get(
            f"{API}/worker/feed",
            params={"latitude": NEAR_LAT, "longitude": NEAR_LNG},
            headers=worker.headers,
        )
    ).json()
    assert any(item["id"] == shift["id"] for item in feed["items"])

    applied = await app_client.post(
        f"{API}/worker/shifts/{shift['id']}/applications",
        json={"cover_note": "I can do it"},
        headers=worker.headers,
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["status"] == "confirmed"
    application_id = applied.json()["id"]

    applicants = (
        await app_client.get(
            f"{API}/business/shifts/{shift['id']}/applications", headers=business.headers
        )
    ).json()
    assert applicants["items"][0]["worker"]["full_name"] == "Meena"

    async def business_applicant_ids(status: str) -> list[str]:
        resp = await app_client.get(
            f"{API}/business/applications", params={"status": status}, headers=business.headers
        )
        assert resp.status_code == 200, resp.text
        return [item["application_id"] for item in resp.json()["items"]]

    assert application_id in await business_applicant_ids("confirmed")
    assert application_id not in await business_applicant_ids("applied")

    detail = (
        await app_client.get(f"{API}/business/shifts/{shift['id']}", headers=business.headers)
    ).json()
    assert detail["status"] == "filled"
    my = (await app_client.get(f"{API}/worker/my-shifts", headers=worker.headers)).json()
    assert my["items"]

    assignment_id = my["items"][0]["assignment_id"]
    no_reason = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/cancel",
        json={"reason": "  "},
        headers=worker.headers,
    )
    assert no_reason.status_code == 400, no_reason.text
    assert no_reason.json()["code"] == "reason_required"
    cancelled = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/cancel",
        json={"reason": "Not feeling well"},
        headers=worker.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["late_cancellation"] is False
    assert cancelled.json()["shift_status"] == "open"
    mine = await app_client.get(
        f"{API}/worker/my-shifts", params={"tab": "applications"}, headers=worker.headers
    )
    withdrawn = next(i for i in mine.json()["items"] if i["shift"]["id"] == shift["id"])
    assert withdrawn["application_status"] == "withdrawn"
    assert withdrawn["assignment_status"] == "cancelled"
    assert withdrawn["responded_at"] is not None
    assert application_id in await business_applicant_ids("rejected")
    assert application_id not in await business_applicant_ids("confirmed")
    again = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/cancel", json={}, headers=worker.headers
    )
    assert again.status_code == 409, again.text


async def _post_scheduled(  # type: ignore[no-untyped-def]
    app_client, business, title: str, starts: datetime, workers_required: int = 1
) -> str:
    resp = await app_client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": title,
            "workers_required": workers_required,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 300,
            "break_minutes": 30,
            "publish": True,
        },
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    await pay_deposit(app_client, business, resp.json()["id"])
    return resp.json()["id"]


async def test_shift_must_be_posted_24h_ahead(app_client, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    starts = (datetime.now(UTC) + timedelta(hours=20)).replace(microsecond=0)
    resp = await app_client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "Too soon",
            "workers_required": 1,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 300,
            "publish": True,
        },
        headers=business.headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "shift_too_soon"


async def test_apply_books_seats_until_full(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    first = await make_worker("Ravi", online=False)
    second = await make_worker("Asha", online=False)
    late = await make_worker("Gopal", online=False)
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    shift_id = await _post_scheduled(app_client, business, "Party helpers", starts, 2)

    for worker in (first, second):
        applied = await app_client.post(
            f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
        )
        assert applied.status_code == 201, applied.text
        assert applied.json()["status"] == "confirmed"

    detail = (
        await app_client.get(f"{API}/business/shifts/{shift_id}", headers=business.headers)
    ).json()
    assert detail["status"] == "filled"
    blocked = await app_client.post(
        f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=late.headers
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "shift_not_recruiting"


async def test_apply_rejects_clash_and_closes_2h_before(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Kiran", online=False)
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    booked = await _post_scheduled(app_client, business, "Booked shift", starts)
    clashing = await _post_scheduled(app_client, business, "Clashing shift", starts)

    resp = await app_client.post(
        f"{API}/worker/shifts/{booked}/applications", json={}, headers=worker.headers
    )
    assert resp.status_code == 201, resp.text
    clash = await app_client.post(
        f"{API}/worker/shifts/{clashing}/applications", json={}, headers=worker.headers
    )
    assert clash.status_code == 409, clash.text
    assert clash.json()["code"] == "overlapping_shift"

    closing = await _post_scheduled(
        app_client, business, "Closing soon", starts + timedelta(days=1)
    )
    soon = datetime.now(UTC) + timedelta(hours=1)
    await db.execute(
        "UPDATE shifts SET starts_at = $2, ends_at = $3 WHERE id = $1",
        UUID(closing),
        soon,
        soon + timedelta(hours=4),
    )
    closed = await app_client.post(
        f"{API}/worker/shifts/{closing}/applications", json={}, headers=worker.headers
    )
    assert closed.status_code == 409, closed.text
    assert closed.json()["code"] == "apply_closed"


async def test_withdrawals_paid_failed_and_idempotent(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker
) -> None:
    worker = await make_worker("Sita", online=False)
    await db.execute(
        "INSERT INTO earning_ledger_entries (worker_profile_id, entry_type, amount_minor, currency,"
        " description) VALUES ($1, 'shift_earning', 50000, 'INR', 'seed')",
        worker.profile_id,
    )
    good = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "upi", "upi_id": "sita@okaxis"},
        headers=worker.headers,
    )
    assert good.status_code == 201, good.text
    assert good.json()["is_default"] is True
    bad_bank = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "bank", "bank_account_number": "12345678901"},
        headers=worker.headers,
    )
    assert bad_bank.status_code == 400
    failing = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "upi", "upi_id": "fail.sita@okaxis"},
        headers=worker.headers,
    )

    too_small = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": good.json()["id"],
            "amount_minor": 100,
            "idempotency_key": "k-small-1",
        },
        headers=worker.headers,
    )
    assert too_small.status_code == 400
    too_big = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": good.json()["id"],
            "amount_minor": 60000,
            "idempotency_key": "k-big-01",
        },
        headers=worker.headers,
    )
    assert too_big.status_code == 409

    body = {
        "payout_account_id": good.json()["id"],
        "amount_minor": 20000,
        "idempotency_key": "k-good-01",
    }
    first = await app_client.post(f"{API}/worker/withdrawals", json=body, headers=worker.headers)
    assert first.status_code == 201, first.text
    retry = await app_client.post(f"{API}/worker/withdrawals", json=body, headers=worker.headers)
    assert retry.json()["id"] == first.json()["id"]

    fail = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": failing.json()["id"],
            "amount_minor": 20000,
            "idempotency_key": "k-fail-01",
        },
        headers=worker.headers,
    )
    assert fail.status_code == 201, fail.text
    summary = (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()
    assert summary["available_minor"] == 10000
    assert summary["in_flight_withdrawals_minor"] == 40000

    await advance_processing_withdrawals(get_pool())

    paid = (
        await app_client.get(
            f"{API}/worker/withdrawals/{first.json()['id']}", headers=worker.headers
        )
    ).json()
    failed = (
        await app_client.get(
            f"{API}/worker/withdrawals/{fail.json()['id']}", headers=worker.headers
        )
    ).json()
    assert paid["status"] == "paid"
    assert failed["status"] == "failed"
    summary = (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()
    assert summary["available_minor"] == 30000  # failed payout reversed
    assert summary["in_flight_withdrawals_minor"] == 0


async def test_payment_webhook_signature(app_client: httpx.AsyncClient) -> None:
    payload = json.dumps(
        {"event_id": "evt_1", "provider_order_id": "nope", "status": "succeeded"}
    ).encode()
    unsigned = await app_client.post(f"{API}/payments/webhooks/fake", content=payload)
    assert unsigned.status_code in (400, 401)
    signature = sign_payload(load_settings().payment_webhook_secret, payload)
    signed = await app_client.post(
        f"{API}/payments/webhooks/fake",
        content=payload,
        headers={"x-kaaamnow-signature": signature, "content-type": "application/json"},
    )
    assert signed.status_code == 200, signed.text
    replay = await app_client.post(
        f"{API}/payments/webhooks/fake",
        content=payload,
        headers={"x-kaaamnow-signature": signature, "content-type": "application/json"},
    )
    assert replay.json()["duplicate"] is True


async def test_support_ticket(app_client: httpx.AsyncClient) -> None:
    user = await login(app_client)
    resp = await app_client.post(
        f"{API}/support/tickets",
        json={
            "topic": "check_in",
            "subject": "Code not working",
            "message": "The code was rejected",
        },
        headers=user.headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "open"


async def test_deposit_covers_final_cost_and_refunds_excess(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Lata", online=False)
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    shift_id = await _post_scheduled(app_client, business, "Deposit shift", starts)
    shift = (
        await app_client.get(f"{API}/business/shifts/{shift_id}", headers=business.headers)
    ).json()
    deposit = (
        await app_client.get(
            f"{API}/business/invoices/{shift['deposit_invoice_id']}", headers=business.headers
        )
    ).json()
    assert deposit["invoice_kind"] == "deposit"
    assert deposit["status"] == "paid"
    assert deposit["total_minor"] == 58406

    applied = await app_client.post(
        f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
    )
    assert applied.status_code == 201, applied.text
    now = datetime.now(UTC)
    await db.execute(
        "UPDATE shifts SET starts_at = $2, ends_at = $3 WHERE id = $1",
        UUID(shift_id),
        now - timedelta(minutes=10),
        now + timedelta(hours=4, minutes=50),
    )
    my = (await app_client.get(f"{API}/worker/my-shifts", headers=worker.headers)).json()
    assignment_id = my["items"][0]["assignment_id"]
    as_worker = (
        await app_client.get(f"{API}/assignments/{assignment_id}", headers=worker.headers)
    ).json()
    assert as_worker["check_in_code"] is None
    code = (
        await app_client.get(f"{API}/assignments/{assignment_id}", headers=business.headers)
    ).json()["check_in_code"]
    assert code and code != shift["check_in_code"]
    checked_in = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-in",
        json={"latitude": 28.6316, "longitude": 77.2168, "check_in_code": code.lower()},
        headers=worker.headers,
    )
    assert checked_in.status_code == 200, checked_in.text
    # Finishing always needs the Business's completion code; the worker never sees it.
    no_code = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out", json={}, headers=worker.headers
    )
    assert no_code.status_code == 422, no_code.text
    as_worker = (
        await app_client.get(f"{API}/assignments/{assignment_id}", headers=worker.headers)
    ).json()
    assert as_worker["completion_code"]["code"] is None
    assert as_worker["completion_code"]["attempts_left"] == 5
    code = await completion_code(app_client, business, assignment_id)
    wrong_code = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out",
        json={"completion_code": "000000" if code != "000000" else "111111"},
        headers=worker.headers,
    )
    assert wrong_code.status_code == 400 and wrong_code.json()["code"] == "completion_code_invalid"
    assert wrong_code.json()["details"]["attempts_left"] == 4
    asked = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/early-end/request", headers=worker.headers
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["early_end_pin"] is None
    pin = (
        await app_client.get(f"{API}/assignments/{assignment_id}", headers=business.headers)
    ).json()["early_end_pin"]
    assert pin
    wrong = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/early-end",
        json={"pin": "0000" if pin != "0000" else "1111"},
        headers=worker.headers,
    )
    assert wrong.status_code == 400, wrong.text
    resp = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/early-end",
        json={"pin": pin},
        headers=worker.headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ended_reason"] == "mutual"
    resp = await app_client.post(
        f"{API}/business/assignments/{assignment_id}/attendance/approve",
        json={"approved_minutes": 180},
        headers=business.headers,
    )
    assert resp.status_code == 200, resp.text

    final = await app_client.post(
        f"{API}/business/shifts/{shift_id}/invoice", headers=business.headers
    )
    assert final.status_code in (200, 201), final.text
    invoice = final.json()
    # 3 h x Rs 120 = Rs 360; + 4% = Rs 374.40; + 2% gateway = Rs 7.49
    assert invoice["invoice_kind"] == "final"
    assert invoice["total_minor"] == 36000 + 1440 + 749 + 749
    assert invoice["tax_minor"] == 749
    assert invoice["status"] == "paid"
    assert invoice["deposit_applied_minor"] == 58406
    assert invoice["amount_due_minor"] == 0
    assert invoice["refund_due_minor"] == 58406 - 38938  # final: Rs 360 + 4% + 2% gateway + 2% tax
    assert {line["line_kind"] for line in invoice["lines"]} == {
        "worker_pay",
        "platform_fee",
        "gateway_fee",
        "tax",
    }

    summary = (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()
    assert summary["available_minor"] == 36000 - 1440


async def test_terms_must_be_accepted_before_posting_and_applying(  # type: ignore[no-untyped-def]
    app_client, db
) -> None:
    from tests.integration.conftest import BUSINESS_LAT, BUSINESS_LNG, signup

    await db.execute(
        "INSERT INTO content_pages (slug, audience, title, body_markdown, effective_date) "
        "VALUES ('terms', 'business', 'Terms', '## Terms', DATE '2026-10-01') "
        "ON CONFLICT (slug, audience) DO NOTHING"
    )

    business = await signup(
        app_client,
        "business",
        {
            "business_name": "No Terms Yet",
            "contact_name": "Owner",
            "business_type_slug": "hospitality",
            "category_slug": "hospitality",
            "address_text": "Block A, Connaught Place",
            "locality": "Connaught Place",
            "latitude": BUSINESS_LAT,
            "longitude": BUSINESS_LNG,
        },
        accept_terms=False,
    )
    status = (await app_client.get(f"{API}/me/terms", headers=business.headers)).json()
    assert {s["audience"]: s["accepted"] for s in status}["business"] is False

    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    body = {
        "shift_type": "scheduled",
        "category_slug": "house-help",
        "job_title": "Needs terms",
        "workers_required": 1,
        "hourly_rate_minor": 12000,
        "starts_at": starts.isoformat(),
        "duration_minutes": 300,
        "publish": True,
    }
    blocked = await app_client.post(f"{API}/business/shifts", json=body, headers=business.headers)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["code"] == "terms_required"

    accepted = await app_client.post(
        f"{API}/me/terms/accept", json={"audience": "business"}, headers=business.headers
    )
    assert accepted.json()["accepted"] is True
    posted = await app_client.post(f"{API}/business/shifts", json=body, headers=business.headers)
    assert posted.status_code == 201, posted.text


async def test_switch_active_role_needs_registered_role(app_client, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Role Switch Cafe")
    missing = await app_client.put(
        f"{API}/me/active-role", json={"role": "worker"}, headers=business.headers
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["code"] == "role_not_registered"

    switched = await app_client.put(
        f"{API}/me/active-role", json={"role": "business"}, headers=business.headers
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["active_role"] == "business"


async def test_business_adds_worker_role_and_switches(app_client, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Two Roles Cafe")
    worker_details = {
        "full_name": "Ignored Name",
        "age": 30,
        "address_text": "Connaught Place, New Delhi",
        "locality": "Connaught Place",
        "latitude": NEAR_LAT,
        "longitude": NEAR_LNG,
        "work_type_slugs": ["hospitality"],
    }
    added = await app_client.post(
        f"{API}/me/roles",
        json={"role": "worker", "worker": worker_details},
        headers=business.headers,
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert sorted(body["me"]["roles"]) == ["business", "worker"]
    assert body["me"]["active_role"] == "worker"
    assert body["me"]["full_name"] == "Owner"
    headers = {"Authorization": f"Bearer {body['tokens']['access_token']}"}

    again = await app_client.post(
        f"{API}/me/roles", json={"role": "worker", "worker": worker_details}, headers=headers
    )
    assert again.status_code == 409
    earnings = await app_client.get(f"{API}/worker/earnings", headers=headers)
    assert earnings.status_code == 200, earnings.text

    back = await app_client.put(f"{API}/me/active-role", json={"role": "business"}, headers=headers)
    assert back.json()["active_role"] == "business"
