"""RazorpayX worker payouts: contact → fund account → payout, status polling, and a refused
payout never debits the worker. The RazorpayX HTTP API is replaced by an in-memory stub."""

from __future__ import annotations

import secrets
from collections.abc import Iterator

import asyncpg
import pytest

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.services.earnings.earnings_sweeps import advance_processing_withdrawals
from app.services.earnings.sources.payout_provider_factory import (
    PayoutProviderError,
    RazorpayXPayoutProvider,
    get_payout_provider,
)

API = "/api/v1"


class _RazorpayXStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []
        self.payouts: dict[str, dict] = {}
        self.reject_payouts = False

    async def request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        self.calls.append((method, path, json, headers))
        if method == "POST" and path == "/contacts":
            return {"id": f"cont_{secrets.token_hex(4)}", **(json or {})}
        if method == "POST" and path == "/fund_accounts":
            return {"id": f"fa_{secrets.token_hex(4)}", **(json or {})}
        if method == "POST" and path == "/payouts":
            if self.reject_payouts:
                raise PayoutProviderError("RazorpayX POST /payouts → 400: insufficient balance")
            payout = {"id": f"pout_{secrets.token_hex(4)}", "status": "processing", **(json or {})}
            self.payouts[payout["id"]] = payout
            return payout
        if method == "GET" and path.startswith("/payouts/"):
            return self.payouts[path.rsplit("/", 1)[1]]
        raise AssertionError(f"unexpected RazorpayX call {method} {path}")


@pytest.fixture
def razorpayx(monkeypatch: pytest.MonkeyPatch) -> Iterator[_RazorpayXStub]:
    settings = load_settings()
    stub = _RazorpayXStub()
    monkeypatch.setattr(settings, "payout_provider", "razorpayx")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_kaaamnow")
    monkeypatch.setattr(settings, "razorpay_key_secret", "test_secret")
    monkeypatch.setattr(settings, "razorpayx_account_number", "2323230000000000")
    monkeypatch.setattr(settings, "razorpay_allow_live_keys", False)
    monkeypatch.setattr(RazorpayXPayoutProvider, "_request", stub.request)
    yield stub


async def test_upi_payout_is_idempotent_and_uses_upi_mode(razorpayx) -> None:  # type: ignore[no-untyped-def]
    provider = get_payout_provider()
    payout_id = await provider.create_payout(
        reference="WD-1",
        amount_minor=25000,
        account={"account_type": "upi", "upi_id": "sita@okaxis", "account_holder_name": "Sita"},
    )
    _, _, body, headers = razorpayx.calls[-1]
    assert body is not None and headers == {"X-Payout-Idempotency": "WD-1"}
    assert body["mode"] == "UPI" and body["amount"] == 25000
    assert body["account_number"] == "2323230000000000"
    fund = razorpayx.calls[1][2]
    assert fund is not None and fund["vpa"] == {"address": "sita@okaxis"}
    assert (await provider.fetch_status(payout_id)).status == "processing"
    razorpayx.payouts[payout_id]["status"] = "processed"
    assert (await provider.fetch_status(payout_id)).status == "paid"


async def test_bank_payout_uses_imps_and_reports_reversal(razorpayx) -> None:  # type: ignore[no-untyped-def]
    provider = get_payout_provider()
    payout_id = await provider.create_payout(
        reference="WD-2",
        amount_minor=10000,
        account={
            "account_type": "bank",
            "bank_account_number": "12345678901",
            "bank_ifsc": "HDFC0000001",
            "account_holder_name": "Ravi",
        },
    )
    assert razorpayx.calls[-1][2]["mode"] == "IMPS"  # type: ignore[index]
    fund = razorpayx.calls[1][2]
    assert fund is not None and fund["bank_account"]["name"] == "Ravi"
    razorpayx.payouts[payout_id].update(
        status="reversed", status_details={"description": "Beneficiary bank down"}
    )
    status = await provider.fetch_status(payout_id)
    assert (status.status, status.failure_reason) == ("failed", "Beneficiary bank down")


async def test_paytm_wallet_is_refused_before_any_call(razorpayx) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PayoutProviderError, match="paytm"):
        await get_payout_provider().create_payout(
            reference="WD-3",
            amount_minor=10000,
            account={"account_type": "paytm", "paytm_phone": "9999999999"},
        )
    assert razorpayx.calls == []


def test_razorpayx_needs_account_number_and_test_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = load_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_unit")
    monkeypatch.setattr(settings, "razorpay_key_secret", "unit_secret")
    monkeypatch.setattr(settings, "razorpayx_account_number", "")
    with pytest.raises(PayoutProviderError, match="RAZORPAYX_ACCOUNT_NUMBER"):
        RazorpayXPayoutProvider()
    monkeypatch.setattr(settings, "razorpayx_account_number", "2323230000000000")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_unit")
    monkeypatch.setattr(settings, "razorpay_allow_live_keys", False)
    with pytest.raises(PayoutProviderError, match="rzp_test_"):
        RazorpayXPayoutProvider()


async def _worker_with_upi(app_client, db: asyncpg.Connection, make_worker):  # type: ignore[no-untyped-def]
    worker = await make_worker("Sita", online=False)
    await db.execute(
        "INSERT INTO earning_ledger_entries (worker_profile_id, entry_type, amount_minor, currency,"
        " description) VALUES ($1, 'shift_earning', 50000, 'INR', 'seed')",
        worker.profile_id,
    )
    account = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "upi", "upi_id": "sita@okaxis"},
        headers=worker.headers,
    )
    assert account.status_code == 201, account.text
    return worker, account.json()["id"]


async def test_withdrawal_is_paid_once_razorpayx_processes_it(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, razorpayx
) -> None:
    worker, account_id = await _worker_with_upi(app_client, db, make_worker)
    created = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": account_id,
            "amount_minor": 20000,
            "idempotency_key": "rzpx-ok-1",
        },
        headers=worker.headers,
    )
    assert created.status_code == 201, created.text
    await advance_processing_withdrawals(get_pool())
    url = f"{API}/worker/withdrawals/{created.json()['id']}"
    assert (await app_client.get(url, headers=worker.headers)).json()["status"] == "processing"

    for payout in razorpayx.payouts.values():
        payout["status"] = "processed"
    await advance_processing_withdrawals(get_pool())
    assert (await app_client.get(url, headers=worker.headers)).json()["status"] == "paid"


async def test_refused_razorpayx_payout_never_debits_the_worker(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, razorpayx
) -> None:
    worker, account_id = await _worker_with_upi(app_client, db, make_worker)
    razorpayx.reject_payouts = True
    refused = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": account_id,
            "amount_minor": 20000,
            "idempotency_key": "rzpx-no-1",
        },
        headers=worker.headers,
    )
    assert refused.status_code == 502
    assert refused.json()["code"] == "payout_provider_error"
    summary = (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()
    assert summary["available_minor"] == 50000
    assert summary["in_flight_withdrawals_minor"] == 0


async def test_withdrawal_is_refused_until_razorpayx_account_is_set(  # type: ignore[no-untyped-def]
    app_client, db: asyncpg.Connection, make_worker, razorpayx, monkeypatch
) -> None:
    worker, account_id = await _worker_with_upi(app_client, db, make_worker)
    monkeypatch.setattr(load_settings(), "razorpayx_account_number", "")
    refused = await app_client.post(
        f"{API}/worker/withdrawals",
        json={
            "payout_account_id": account_id,
            "amount_minor": 20000,
            "idempotency_key": "rzpx-noacct",
        },
        headers=worker.headers,
    )
    assert refused.status_code == 502
    assert refused.json()["code"] == "payout_provider_error"
    assert razorpayx.calls == []
    summary = (await app_client.get(f"{API}/worker/earnings", headers=worker.headers)).json()
    assert summary["available_minor"] == 50000
