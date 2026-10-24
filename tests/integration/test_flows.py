"""End-to-end Figma flows against a real database."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.services.billing.validation.webhook_signature import sign_payload
from app.services.earnings.earnings_sweeps import advance_processing_withdrawals
from app.services.users.deletion_service import process_deletion_requests
from tests.integration.conftest import NEAR_LAT, NEAR_LNG, login

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
    resp = await client.post(
        f"{API}/worker/assignments/{assignment_id}/check-out", json={}, headers=worker.headers
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
    assert "1 active shifts" in request["blockers"]
    assert await db.fetchval("SELECT is_active FROM users WHERE id = $1", business.user_id)

    # An approved request must be rechecked when the background processor runs.
    await db.execute(
        "UPDATE account_deletion_requests SET status = 'approved', approved_at = now() "
        "WHERE id = $1",
        request["id"],
    )
    assert await process_deletion_requests(get_pool()) == 0
    assert await db.fetchval("SELECT is_active FROM users WHERE id = $1", business.user_id)

    cancelled = await app_client.post(
        f"{API}/business/shifts/{shift['id']}/cancel",
        json={},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
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
    assert summary["available_minor"] == 45000
    assert summary["lifetime_minor"] == 45000
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
    assert shift["status"] == "open"

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

    applied_page = (
        await app_client.get(f"{API}/business/applications", headers=business.headers)
    ).json()
    assert applied_page["items"][0]["shift"]["id"] == shift["id"]
    assert applied_page["items"][0]["worker"]["full_name"] == "Meena"

    selected = await app_client.post(
        f"{API}/business/applications/{application_id}/select", headers=business.headers
    )
    assert selected.status_code == 200, selected.text
    assert application_id in await business_applicant_ids("selected")
    assert application_id not in await business_applicant_ids("applied")
    confirmed = await app_client.post(
        f"{API}/worker/applications/{application_id}/confirm", headers=worker.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    assert application_id in await business_applicant_ids("confirmed")

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


async def test_worker_cannot_withdraw_inside_cutoff(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Arjun", online=False)
    starts = (datetime.now(UTC) + timedelta(hours=6)).replace(microsecond=0)
    shift = await app_client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "Evening help",
            "workers_required": 1,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 240,
            "break_minutes": 0,
            "publish": True,
        },
        headers=business.headers,
    )
    assert shift.status_code == 201, shift.text
    applied = await app_client.post(
        f"{API}/worker/shifts/{shift.json()['id']}/applications", json={}, headers=worker.headers
    )
    assert applied.status_code == 201, applied.text
    application_id = applied.json()["id"]
    for path, headers in (
        (f"business/applications/{application_id}/select", business.headers),
        (f"worker/applications/{application_id}/confirm", worker.headers),
    ):
        resp = await app_client.post(f"{API}/{path}", headers=headers)
        assert resp.status_code == 200, resp.text
    my = (await app_client.get(f"{API}/worker/my-shifts", headers=worker.headers)).json()
    assignment_id = my["items"][0]["assignment_id"]

    blocked = await app_client.post(
        f"{API}/worker/assignments/{assignment_id}/cancel",
        json={"reason": "Something came up"},
        headers=worker.headers,
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "cancellation_cutoff"


async def test_business_rejected_applicants(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    rejected_worker = await make_worker("Ravi", online=False)
    declining_worker = await make_worker("Asha", online=False)
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    resp = await app_client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "Party helpers",
            "workers_required": 2,
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

    application_ids = {}
    for name, worker in (("rejected", rejected_worker), ("declining", declining_worker)):
        applied = await app_client.post(
            f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
        )
        assert applied.status_code == 201, applied.text
        application_ids[name] = applied.json()["id"]

    rejected = await app_client.post(
        f"{API}/business/applications/{application_ids['rejected']}/reject",
        headers=business.headers,
    )
    assert rejected.status_code == 200, rejected.text
    selected = await app_client.post(
        f"{API}/business/applications/{application_ids['declining']}/select",
        headers=business.headers,
    )
    assert selected.status_code == 200, selected.text
    declined = await app_client.post(
        f"{API}/worker/applications/{application_ids['declining']}/decline",
        headers=declining_worker.headers,
    )
    assert declined.status_code == 200, declined.text

    page = await app_client.get(
        f"{API}/business/applications", params={"status": "rejected"}, headers=business.headers
    )
    assert page.status_code == 200, page.text
    statuses = {item["application_id"]: item["status"] for item in page.json()["items"]}
    assert statuses == {
        application_ids["rejected"]: "rejected",
        application_ids["declining"]: "declined",
    }


async def test_clashing_offer_stays_open_for_worker_to_decline(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker
) -> None:
    business = await make_business()
    worker = await make_worker("Kiran", online=False)
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)

    async def create_shift(title: str) -> str:
        resp = await app_client.post(
            f"{API}/business/shifts",
            json={
                "shift_type": "scheduled",
                "category_slug": "house-help",
                "job_title": title,
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
        return resp.json()["id"]

    async def apply(shift_id: str) -> str:
        resp = await app_client.post(
            f"{API}/worker/shifts/{shift_id}/applications", json={}, headers=worker.headers
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    booked_app = await apply(await create_shift("Booked shift"))
    clashing_app = await apply(await create_shift("Clashing shift"))
    for application_id in (booked_app, clashing_app):
        resp = await app_client.post(
            f"{API}/business/applications/{application_id}/select", headers=business.headers
        )
        assert resp.status_code == 200, resp.text

    confirmed = await app_client.post(
        f"{API}/worker/applications/{booked_app}/confirm", headers=worker.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    clash = await app_client.post(
        f"{API}/worker/applications/{clashing_app}/confirm", headers=worker.headers
    )
    assert clash.status_code == 409, clash.text
    assert clash.json()["code"] == "overlapping_shift"
    my_applications = (
        await app_client.get(
            f"{API}/worker/my-shifts", params={"tab": "applications"}, headers=worker.headers
        )
    ).json()
    assert {i["application_id"]: i["application_status"] for i in my_applications["items"]} == {
        clashing_app: "selected"
    }

    declined = await app_client.post(
        f"{API}/worker/applications/{clashing_app}/decline", headers=worker.headers
    )
    assert declined.status_code == 200, declined.text
    rejected_page = (
        await app_client.get(
            f"{API}/business/applications",
            params={"status": "rejected"},
            headers=business.headers,
        )
    ).json()
    assert {item["application_id"]: item["status"] for item in rejected_page["items"]} == {
        clashing_app: "declined"
    }

    late_app = await apply(await create_shift("Applied after booking"))
    blocked = await app_client.post(
        f"{API}/business/applications/{late_app}/select", headers=business.headers
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "worker_unavailable"


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
