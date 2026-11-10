"""Manual payouts: the worker requests, an admin pays outside the app and marks it paid with a
screenshot, or rejects it and the amount goes back to the worker's balance."""

from __future__ import annotations

from uuid import UUID

import asyncpg
import httpx
import pytest

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.services.earnings.earnings_sweeps import advance_processing_withdrawals
from tests.integration.test_admin_crud import _admin

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
SEED = 50000


@pytest.fixture
def manual_payouts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_settings(), "payout_provider", "manual")


async def _request(app_client: httpx.AsyncClient, db: asyncpg.Connection, make_worker, amount: int):  # type: ignore[no-untyped-def]
    worker = await make_worker("Sita", online=False)
    await db.execute(
        "INSERT INTO earning_ledger_entries (worker_profile_id, entry_type, amount_minor, currency,"
        " description) VALUES ($1, 'shift_earning', $2, 'INR', 'seed')",
        worker.profile_id,
        SEED,
    )
    account = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "upi", "upi_id": "sita@okaxis"},
        headers=worker.headers,
    )
    assert account.status_code == 201, account.text
    created = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": account.json()["id"],
            "amount_minor": amount,
            "idempotency_key": f"manual-{amount}",
        },
        headers=worker.headers,
    )
    return worker, created


async def _summary(app_client: httpx.AsyncClient, worker) -> dict:  # type: ignore[no-untyped-def]
    return (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()


async def _kinds(db: asyncpg.Connection, user_id: UUID) -> list[tuple[str, str]]:
    rows = await db.fetch(
        "SELECT kind, body FROM notifications WHERE user_id = $1 AND kind LIKE 'withdrawal%'",
        user_id,
    )
    return [(r["kind"], r["body"]) for r in rows]


async def test_admin_marks_a_manual_withdrawal_paid_with_a_screenshot(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, manual_payouts
) -> None:
    worker, created = await _request(app_client, db, make_worker, 20000)
    assert created.status_code == 201, created.text
    withdrawal = created.json()
    assert withdrawal["status"] == "processing"
    summary = await _summary(app_client, worker)
    assert summary["available_minor"] == SEED - 20000
    assert summary["in_flight_withdrawals_minor"] == 20000

    await advance_processing_withdrawals(get_pool())
    url = f"{API}/worker/withdrawals/{withdrawal['id']}"
    assert (await app_client.get(url, headers=worker.headers)).json()["status"] == "processing"

    paid_url = f"{API}/admin/withdrawals/{withdrawal['id']}/mark-paid"
    proof = {"proof": ("proof.png", PNG, "image/png")}
    assert (await app_client.post(paid_url, files=proof, headers=worker.headers)).status_code == 403
    admin = await _admin(app_client, db)
    missing = await app_client.post(paid_url, data={"utr": "1"}, headers=admin.headers)
    assert missing.status_code == 422
    wrong = await app_client.post(
        paid_url, files={"proof": ("p.gif", PNG, "image/gif")}, headers=admin.headers
    )
    assert wrong.status_code == 400

    paid = await app_client.post(
        paid_url, files=proof, data={"utr": " 412345678901 "}, headers=admin.headers
    )
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "paid"
    assert body["payout_utr"] == "412345678901"
    assert body["proof_url"]

    seen = (await app_client.get(url, headers=worker.headers)).json()
    assert (seen["status"], seen["payout_utr"]) == ("paid", "412345678901")
    summary = await _summary(app_client, worker)
    assert summary["available_minor"] == SEED - 20000
    assert summary["in_flight_withdrawals_minor"] == 0
    kinds = await _kinds(db, worker.user_id)
    assert [k for k, _ in kinds] == ["withdrawal_paid"]
    assert "UTR 412345678901" in kinds[0][1]
    audit = await db.fetchval(
        "SELECT count(*) FROM admin_audit_log WHERE resource = 'withdrawals' AND record_id = $1",
        withdrawal["id"],
    )
    assert audit == 1

    again = await app_client.post(paid_url, files=proof, headers=admin.headers)
    assert again.status_code == 409
    reject = await app_client.post(
        f"{API}/admin/withdrawals/{withdrawal['id']}/reject",
        json={"reason": "Changed my mind"},
        headers=admin.headers,
    )
    assert reject.status_code == 409


async def test_admin_rejects_a_manual_withdrawal_and_the_money_returns(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, manual_payouts
) -> None:
    worker, created = await _request(app_client, db, make_worker, 15000)
    withdrawal_id = created.json()["id"]
    admin = await _admin(app_client, db)
    reject_url = f"{API}/admin/withdrawals/{withdrawal_id}/reject"
    short = await app_client.post(reject_url, json={"reason": "  no "}, headers=admin.headers)
    assert short.status_code == 422

    rejected = await app_client.post(
        reject_url, json={"reason": "UPI ID is not valid"}, headers=admin.headers
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "failed"
    assert rejected.json()["failure_reason"] == "UPI ID is not valid"
    summary = await _summary(app_client, worker)
    assert summary["available_minor"] == SEED
    assert summary["in_flight_withdrawals_minor"] == 0
    reversal = await db.fetchval(
        "SELECT amount_minor FROM earning_ledger_entries"
        " WHERE withdrawal_id = $1 AND entry_type = 'withdrawal_reversal'",
        UUID(withdrawal_id),
    )
    assert reversal == 15000
    assert [k for k, _ in await _kinds(db, worker.user_id)] == ["withdrawal_failed"]


async def test_worker_cannot_withdraw_more_than_available(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, manual_payouts
) -> None:
    worker, created = await _request(app_client, db, make_worker, SEED + 1)
    assert created.status_code == 409
    assert created.json()["code"] == "insufficient_balance"
    assert (await _summary(app_client, worker))["available_minor"] == SEED


async def test_provider_withdrawals_cannot_be_settled_manually(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, monkeypatch
) -> None:
    monkeypatch.setattr(load_settings(), "payout_provider", "fake")
    _, created = await _request(app_client, db, make_worker, 10000)
    admin = await _admin(app_client, db)
    paid = await app_client.post(
        f"{API}/admin/withdrawals/{created.json()['id']}/mark-paid",
        files={"proof": ("proof.png", PNG, "image/png")},
        headers=admin.headers,
    )
    assert paid.status_code == 409
    assert paid.json()["code"] == "withdrawal_not_manual"


async def test_admin_sets_the_minimum_withdrawal(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, manual_payouts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load_settings(), "min_withdrawal_minor", 10000)
    admin = await _admin(app_client, db)
    effective_url = f"{API}/admin/settings/payouts"
    default = load_settings().min_withdrawal_minor
    worker, too_small = await _request(app_client, db, make_worker, 100)
    try:
        effective = await app_client.get(effective_url, headers=admin.headers)
        assert effective.json() == {"min_withdrawal_minor": default, "source": "default"}
        assert too_small.status_code == 400, too_small.text
        assert too_small.json()["code"] == "withdrawal_below_min"

        out_of_range = await app_client.post(
            f"{API}/admin/payout_settings",
            json={"min_withdrawal_minor": 99, "notes": "too low"},
            headers=admin.headers,
        )
        assert out_of_range.status_code == 400, out_of_range.text
        created = await app_client.post(
            f"{API}/admin/payout_settings",
            json={"min_withdrawal_minor": 100, "notes": "Allow ₹1 withdrawals"},
            headers=admin.headers,
        )
        assert created.status_code == 201, created.text
        effective = await app_client.get(effective_url, headers=admin.headers)
        assert effective.json() == {"min_withdrawal_minor": 100, "source": "admin"}
        assert (await _summary(app_client, worker))["min_withdrawal_minor"] == 100

        account_id = (
            await app_client.get(f"{API}/worker/payout-accounts", headers=worker.headers)
        ).json()[0]["id"]
        allowed = await app_client.post(
            f"{API}/worker/withdrawals",
            json={
                "payout_account_id": account_id,
                "amount_minor": 100,
                "idempotency_key": "one-rupee",
            },
            headers=worker.headers,
        )
        assert allowed.status_code == 201, allowed.text

        raised = await app_client.patch(
            f"{API}/admin/payout_settings/{created.json()['id']}",
            json={"min_withdrawal_minor": 500000, "notes": "₹5,000 minimum"},
            headers=admin.headers,
        )
        assert raised.status_code == 200, raised.text
        assert (await _summary(app_client, worker))["min_withdrawal_minor"] == 500000
        assert (
            await db.fetchval(
                "SELECT count(*) FROM admin_audit_log WHERE resource = 'payout_settings'"
            )
            == 2
        )
        assert (await app_client.get(effective_url, headers=worker.headers)).status_code == 403
    finally:
        await db.execute("DELETE FROM payout_settings")


async def test_worker_adds_and_removes_upi_qr(app_client: httpx.AsyncClient, make_worker) -> None:  # type: ignore[no-untyped-def]
    worker = await make_worker("Gita", online=False)
    other = await make_worker("Mira", online=False)
    account = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "upi", "upi_id": "gita@okaxis"},
        headers=worker.headers,
    )
    assert account.status_code == 201, account.text
    assert account.json()["upi_qr_url"] is None
    qr_url = f"{API}/worker/payout-accounts/{account.json()['id']}/qr"

    not_image = await app_client.put(
        qr_url, files={"file": ("qr.png", b"hello", "image/png")}, headers=worker.headers
    )
    assert not_image.status_code == 400
    not_mine = await app_client.put(
        qr_url, files={"file": ("qr.png", PNG, "image/png")}, headers=other.headers
    )
    assert not_mine.status_code == 404

    added = await app_client.put(
        qr_url, files={"file": ("qr.png", PNG, "image/png")}, headers=worker.headers
    )
    assert added.status_code == 200, added.text
    assert "/upi-qr/" in added.json()["upi_qr_url"]

    same_upi = await app_client.patch(
        f"{API}/worker/payout-accounts/{account.json()['id']}",
        json={"upi_id": "gita@okaxis", "account_holder_name": "Gita"},
        headers=worker.headers,
    )
    assert same_upi.json()["upi_qr_url"] == added.json()["upi_qr_url"]
    new_upi = await app_client.patch(
        f"{API}/worker/payout-accounts/{account.json()['id']}",
        json={"upi_id": "gita@ybl"},
        headers=worker.headers,
    )
    assert new_upi.json()["upi_qr_url"] is None, "an old QR must not point at a new UPI ID"

    await app_client.put(
        qr_url, files={"file": ("qr.png", PNG, "image/png")}, headers=worker.headers
    )
    removed = await app_client.delete(qr_url, headers=worker.headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["upi_qr_url"] is None
