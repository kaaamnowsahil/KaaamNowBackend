"""Razorpay Standard Checkout: order → Checkout handler verify, and webhooks. The Razorpay
HTTP API is replaced by an in-memory stub."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.config.settings import load_settings
from app.services.billing.sources.payment_provider_factory import RazorpayPaymentProvider
from app.services.billing.validation.webhook_signature import sign_payload

API = "/api/v1"
KEY_ID = "rzp_test_kaaamnow"
KEY_SECRET = "test_secret"
WEBHOOK_SECRET = "whsec_test"


class _RazorpayStub:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.payments: dict[str, list[dict]] = {}

    async def request(self, method: str, path: str, json: dict | None = None) -> dict:
        if method == "POST" and path == "/orders":
            order_id = f"order_{secrets.token_hex(6)}"
            self.orders[order_id] = {"id": order_id, **(json or {})}
            self.payments[order_id] = []
            return self.orders[order_id]
        if method == "GET" and path.endswith("/payments"):
            return {"items": self.payments[path.split("/")[2]]}
        if method == "POST" and path.endswith("/capture"):
            payment_id = path.split("/")[2]
            for items in self.payments.values():
                for payment in items:
                    if payment["id"] == payment_id:
                        payment["status"] = "captured"
                        return payment
        raise AssertionError(f"unexpected Razorpay call {method} {path}")

    def pay(self, order_id: str, status: str = "authorized") -> str:
        payment_id = f"pay_{order_id[-6:]}"
        amount = self.orders[order_id]["amount"]
        self.payments[order_id].append(
            {"id": payment_id, "status": status, "amount": amount, "currency": "INR"}
        )
        return payment_id


@pytest.fixture
def razorpay(monkeypatch: pytest.MonkeyPatch) -> Iterator[_RazorpayStub]:
    settings = load_settings()
    stub = _RazorpayStub()
    monkeypatch.setattr(settings, "payment_provider", "razorpay")
    monkeypatch.setattr(settings, "razorpay_key_id", KEY_ID)
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "payment_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(RazorpayPaymentProvider, "_request", stub.request)
    yield stub


async def _deposit_payment(client: httpx.AsyncClient, business) -> tuple[str, dict]:  # type: ignore[no-untyped-def]
    starts = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    shift = await client.post(
        f"{API}/business/shifts",
        json={
            "shift_type": "scheduled",
            "category_slug": "house-help",
            "job_title": "Razorpay shift",
            "workers_required": 1,
            "hourly_rate_minor": 12000,
            "starts_at": starts.isoformat(),
            "duration_minutes": 300,
            "publish": True,
        },
        headers=business.headers,
    )
    assert shift.status_code == 201, shift.text
    payment = await client.post(
        f"{API}/business/invoices/{shift.json()['deposit_invoice_id']}/payments",
        json={"method": "card_netbanking"},
        headers=business.headers,
    )
    assert payment.status_code == 201, payment.text
    return shift.json()["id"], payment.json()


async def _shift_status(client: httpx.AsyncClient, business, shift_id: str) -> str:  # type: ignore[no-untyped-def]
    shift = await client.get(f"{API}/business/shifts/{shift_id}", headers=business.headers)
    return shift.json()["status"]


async def test_checkout_verify_captures_and_opens_shift(  # type: ignore[no-untyped-def]
    app_client, make_business, razorpay
) -> None:
    business = await make_business()
    shift_id, payment = await _deposit_payment(app_client, business)
    assert payment["provider"] == "razorpay"
    assert payment["checkout_key"] == KEY_ID
    order_id = payment["provider_order_id"]
    assert razorpay.orders[order_id]["amount"] == payment["amount_minor"]

    payment_id = razorpay.pay(order_id)
    forged = await app_client.post(
        f"{API}/business/payments/{payment['id']}/razorpay-verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": "0" * 64,
        },
        headers=business.headers,
    )
    assert forged.status_code == 400, forged.text

    signature = hmac.new(
        KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    verified = await app_client.post(
        f"{API}/business/payments/{payment['id']}/razorpay-verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
        headers=business.headers,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "succeeded"
    assert razorpay.payments[order_id][0]["status"] == "captured"
    assert await _shift_status(app_client, business, shift_id) == "open"


async def test_webhook_settles_even_after_local_expiry(  # type: ignore[no-untyped-def]
    app_client, db, make_business, razorpay
) -> None:
    business = await make_business()
    shift_id, payment = await _deposit_payment(app_client, business)
    await db.execute("UPDATE payments SET status = 'expired' WHERE id = $1::uuid", payment["id"])
    payment_id = razorpay.pay(payment["provider_order_id"], status="captured")
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": payment["provider_order_id"],
                        "status": "captured",
                    }
                }
            },
        }
    ).encode()
    headers = {"x-razorpay-event-id": f"evt_{payment_id}"}

    unsigned = await app_client.post(
        f"{API}/payments/webhooks/razorpay", content=body, headers=headers
    )
    assert unsigned.status_code == 401, unsigned.text

    headers["x-razorpay-signature"] = sign_payload(WEBHOOK_SECRET, body)
    first = await app_client.post(
        f"{API}/payments/webhooks/razorpay", content=body, headers=headers
    )
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False
    again = await app_client.post(
        f"{API}/payments/webhooks/razorpay", content=body, headers=headers
    )
    assert again.json()["duplicate"] is True
    assert await _shift_status(app_client, business, shift_id) == "open"
