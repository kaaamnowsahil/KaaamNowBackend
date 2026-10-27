"""Admin dashboard CRUD + metrics against a real database."""

from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from tests.integration.conftest import TEST_OTP, Actor, login, next_phone

pytestmark = pytest.mark.asyncio(loop_scope="session")

ADMIN = "/api/v1/admin"


async def _admin(client: httpx.AsyncClient, db: asyncpg.Connection) -> Actor:
    """Sign in, grant the admin role in SQL, then refresh so the JWT carries it."""
    phone = next_phone()
    await db.execute("INSERT INTO users (phone) VALUES ($1) ON CONFLICT (phone) DO NOTHING", phone)
    await client.post("/api/v1/auth/otp/send", json={"phone": phone})
    verified = await client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": TEST_OTP})
    assert verified.status_code == 200, verified.text
    body = verified.json()
    user_id = UUID(body["me"]["id"])
    await db.execute(
        "INSERT INTO user_roles (user_id, role) VALUES ($1, 'admin') ON CONFLICT DO NOTHING",
        user_id,
    )
    refreshed = await client.post(
        "/api/v1/auth/token/refresh", json={"refresh_token": body["tokens"]["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    token = refreshed.json()["access_token"]
    return Actor(phone=phone, user_id=user_id, headers={"Authorization": f"Bearer {token}"})


async def test_admin_requires_admin_role(app_client: httpx.AsyncClient) -> None:
    user = await login(app_client)
    resp = await app_client.get(f"{ADMIN}/resources", headers=user.headers)
    assert resp.status_code == 403, resp.text
    assert (await app_client.get(f"{ADMIN}/users")).status_code == 401


async def test_resources_metadata(app_client: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    admin = await _admin(app_client, db)
    resp = await app_client.get(f"{ADMIN}/resources", headers=admin.headers)
    assert resp.status_code == 200, resp.text
    by_name = {r["name"]: r for r in resp.json()["items"]}
    assert {"users", "faq_entries", "earning_ledger_entries", "otp_challenges"} <= set(by_name)
    assert by_name["earning_ledger_entries"]["operations"] == []
    assert by_name["payments"]["operations"] == []
    assert by_name["withdrawals"]["operations"] == []
    assert by_name["work_categories"]["delete_mode"] == "soft"
    assert by_name["shifts"]["delete_mode"] == "hard"
    otp_columns = {c["name"] for c in by_name["otp_challenges"]["columns"]}
    assert "code_hash" not in otp_columns
    worker_cols = {c["name"]: c for c in by_name["worker_profiles"]["columns"]}
    assert worker_cols["rating_avg"]["read_only"] is True
    assert worker_cols["locality"]["writable_on_update"] is True


async def test_work_category_crud_and_export(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    admin = await _admin(app_client, db)
    slug = f"admin-{uuid4().hex[:8]}"
    created = await app_client.post(
        f"{ADMIN}/work_categories",
        json={"slug": slug, "name": "Admin Made", "sort_order": "7"},
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["slug"] == slug and row["sort_order"] == 7 and row["is_active"] is True

    dup = await app_client.post(
        f"{ADMIN}/work_categories", json={"slug": slug, "name": "Dup"}, headers=admin.headers
    )
    assert dup.status_code == 409 and dup.json()["code"] == "admin_unique_violation"

    bad = await app_client.post(
        f"{ADMIN}/work_categories", json={"id": str(uuid4()), "name": "x"}, headers=admin.headers
    )
    assert bad.status_code == 400 and bad.json()["code"] == "admin_invalid_fields"

    listed = await app_client.get(
        f"{ADMIN}/work_categories",
        params={"q": slug, "is_active": "true", "sort": "-sort_order"},
        headers=admin.headers,
    )
    assert listed.status_code == 200, listed.text
    page = listed.json()
    assert page["total"] == 1 and page["items"][0]["id"] == row["id"]

    patched = await app_client.patch(
        f"{ADMIN}/work_categories/{row['id']}", json={"name": "Renamed"}, headers=admin.headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["updated_at"] >= row["updated_at"]

    export = await app_client.get(
        f"{ADMIN}/work_categories/export.csv", params={"q": slug}, headers=admin.headers
    )
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    lines = export.text.strip().splitlines()
    assert lines[0].startswith("id,") and len(lines) == 2 and "Renamed" in lines[1]

    deleted = await app_client.delete(f"{ADMIN}/work_categories/{row['id']}", headers=admin.headers)
    assert deleted.status_code == 204
    fetched = await app_client.get(f"{ADMIN}/work_categories/{row['id']}", headers=admin.headers)
    assert fetched.status_code == 200 and fetched.json()["is_active"] is False


async def test_faq_hard_fields_and_errors(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    admin = await _admin(app_client, db)
    check = await app_client.post(
        f"{ADMIN}/faq_entries",
        json={"audience": "nobody", "question": "Q?", "answer": "A"},
        headers=admin.headers,
    )
    assert check.status_code == 400 and check.json()["code"] == "admin_check_violation"

    wrong_type = await app_client.post(
        f"{ADMIN}/faq_entries",
        json={"audience": "all", "question": "Q?", "answer": "A", "sort_order": "abc"},
        headers=admin.headers,
    )
    assert wrong_type.status_code == 400 and wrong_type.json()["code"] == "admin_invalid_value"

    bad_sort = await app_client.get(
        f"{ADMIN}/faq_entries", params={"sort": "nope"}, headers=admin.headers
    )
    assert bad_sort.status_code == 400
    bad_filter = await app_client.get(
        f"{ADMIN}/faq_entries", params={"nope": "1"}, headers=admin.headers
    )
    assert bad_filter.status_code == 400
    assert (await app_client.get(f"{ADMIN}/nope", headers=admin.headers)).status_code == 404
    missing = await app_client.get(f"{ADMIN}/faq_entries/{uuid4()}", headers=admin.headers)
    assert missing.status_code == 404
    assert (
        await app_client.get(f"{ADMIN}/faq_entries/not-a-uuid", headers=admin.headers)
    ).status_code == 400


async def test_read_only_resources_and_notifications(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    admin = await _admin(app_client, db)
    ledger = await app_client.post(
        f"{ADMIN}/earning_ledger_entries", json={}, headers=admin.headers
    )
    assert ledger.status_code == 403
    pay = await app_client.delete(f"{ADMIN}/payments/{uuid4()}", headers=admin.headers)
    assert pay.status_code == 403
    for resource in ("payments", "withdrawals"):
        forged = await app_client.patch(
            f"{ADMIN}/{resource}/{uuid4()}",
            json={"status": "succeeded" if resource == "payments" else "paid"},
            headers=admin.headers,
        )
        assert forged.status_code == 403, forged.text

    sent = await app_client.post(
        f"{ADMIN}/notifications",
        json={
            "user_id": str(admin.user_id),
            "kind": "admin_message",
            "title": "Hello",
            "data": {"x": 1},
        },
        headers=admin.headers,
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["push_status"] == "pending"
    assert body["data"] == {"kind": "admin_message", "x": 1}
    inbox = await app_client.get("/api/v1/notifications", headers=admin.headers)
    assert any(n["id"] == body["id"] for n in inbox.json()["items"])

    users = await app_client.get(
        f"{ADMIN}/users", params={"phone": admin.phone}, headers=admin.headers
    )
    assert users.json()["total"] == 1

    fk = await app_client.post(
        f"{ADMIN}/user_roles",
        json={"user_id": str(uuid4()), "role": "worker"},
        headers=admin.headers,
    )
    assert fk.status_code == 409 and fk.json()["code"] == "admin_foreign_key_violation"


async def test_composite_key_resource(
    app_client: httpx.AsyncClient, db: asyncpg.Connection, make_worker
) -> None:  # type: ignore[no-untyped-def]
    admin = await _admin(app_client, db)
    worker = await make_worker(online=False)
    rows = await app_client.get(
        f"{ADMIN}/worker_work_categories",
        params={"worker_profile_id": str(worker.profile_id)},
        headers=admin.headers,
    )
    assert rows.status_code == 200 and rows.json()["total"] == 2
    item = rows.json()["items"][0]
    key = f"{item['worker_profile_id']},{item['category_id']}"
    got = await app_client.get(f"{ADMIN}/worker_work_categories/{key}", headers=admin.headers)
    assert got.status_code == 200
    gone = await app_client.delete(f"{ADMIN}/worker_work_categories/{key}", headers=admin.headers)
    assert gone.status_code == 204
    again = await app_client.get(f"{ADMIN}/worker_work_categories/{key}", headers=admin.headers)
    assert again.status_code == 404


async def test_metrics_overview(app_client: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    admin = await _admin(app_client, db)
    resp = await app_client.get(f"{ADMIN}/metrics/overview", headers=admin.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["users_total"] >= 1
    assert isinstance(body["workers_by_verification"], list)
    assert "platform_fees_minor" in body


async def test_support_ticket_closure_is_server_authoritative(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    admin = await _admin(app_client, db)
    user = await login(app_client)
    created = await app_client.post(
        "/api/v1/support/tickets",
        json={"topic": "payout", "subject": "Missing payout", "message": "Not received yet"},
        headers=user.headers,
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]
    url = f"{ADMIN}/support-tickets/{ticket_id}/status"

    # Non-admins and the generic CRUD cannot close or forge resolution fields.
    denied = await app_client.post(url, json={"status": "closed"}, headers=user.headers)
    assert denied.status_code == 403
    forged = await app_client.patch(
        f"{ADMIN}/support_tickets/{ticket_id}",
        json={"status": "closed", "resolved_at": "2020-01-01T00:00:00Z"},
        headers=admin.headers,
    )
    assert forged.status_code == 400, forged.text
    extra = await app_client.post(
        url, json={"status": "closed", "resolved_at": "2020-01-01T00:00:00Z"}, headers=admin.headers
    )
    assert extra.status_code == 422

    started = await app_client.post(url, json={"status": "in_progress"}, headers=admin.headers)
    assert started.status_code == 200 and started.json()["status"] == "in_progress"
    assert started.json()["resolved_at"] is None

    closed = await app_client.post(
        url, json={"status": "closed", "resolution_note": " Paid manually "}, headers=admin.headers
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "closed"
    assert body["resolved_by_user_id"] == str(admin.user_id)
    assert body["resolution_note"] == "Paid manually"
    db_now = await db.fetchval("SELECT now()")
    resolved_at = await db.fetchval(
        "SELECT resolved_at FROM support_tickets WHERE id = $1", UUID(ticket_id)
    )
    assert abs((db_now - resolved_at).total_seconds()) < 60

    again = await app_client.post(url, json={"status": "closed"}, headers=admin.headers)
    assert again.status_code == 200
    assert again.json()["resolved_at"] == body["resolved_at"]
    reopen = await app_client.post(url, json={"status": "in_progress"}, headers=admin.headers)
    assert reopen.status_code == 409

    audits = await db.fetchval(
        "SELECT count(*) FROM admin_audit_log "
        "WHERE resource = 'support_tickets' AND record_id = $1",
        ticket_id,
    )
    assert audits == 2
    missing = await app_client.post(
        f"{ADMIN}/support-tickets/{uuid4()}/status",
        json={"status": "closed"},
        headers=admin.headers,
    )
    assert missing.status_code == 404
