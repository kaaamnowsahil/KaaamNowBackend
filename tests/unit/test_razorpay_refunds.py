"""Razorpay refund adapter: a retried refund with the same key never refunds twice."""

from __future__ import annotations

import pytest

from app.config.settings import load_settings
from app.services.billing.sources.payment_provider_factory import RazorpayPaymentProvider


class _Stub:
    def __init__(self) -> None:
        self.refunds: list[dict] = []
        self.posts = 0

    async def request(self, method: str, path: str, json: dict | None = None) -> dict:
        if method == "GET" and path == "/payments/pay_1/refunds":
            return {"items": self.refunds}
        if method == "POST" and path == "/payments/pay_1/refund":
            self.posts += 1
            row = {"id": f"rfnd_{self.posts}", "status": "pending", **(json or {})}
            self.refunds.append(row)
            return row
        if method == "GET" and path.startswith("/payments/pay_1/refunds/"):
            row = next(r for r in self.refunds if r["id"] == path.rsplit("/", 1)[1])
            return {**row, "status": "processed"}
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> tuple[RazorpayPaymentProvider, _Stub]:
    settings = load_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_unit")
    monkeypatch.setattr(settings, "razorpay_key_secret", "unit_secret")
    stub = _Stub()
    monkeypatch.setattr(RazorpayPaymentProvider, "_request", stub.request)
    return RazorpayPaymentProvider(), stub


async def test_refund_is_created_once_per_key(provider) -> None:  # type: ignore[no-untyped-def]
    rp, stub = provider
    first = await rp.refund(provider_payment_id="pay_1", amount_minor=5000, idempotency_key="k1")
    again = await rp.refund(provider_payment_id="pay_1", amount_minor=5000, idempotency_key="k1")
    assert stub.posts == 1
    assert first.refund_id == again.refund_id == "rfnd_1"
    assert first.status == "pending"
    other = await rp.refund(provider_payment_id="pay_1", amount_minor=100, idempotency_key="k2")
    assert stub.posts == 2 and other.refund_id == "rfnd_2"
    assert stub.refunds[0]["notes"] == {"kn_refund_key": "k1"}
    assert stub.refunds[0]["amount"] == 5000


async def test_fetch_refund_maps_status(provider) -> None:  # type: ignore[no-untyped-def]
    rp, _ = provider
    created = await rp.refund(provider_payment_id="pay_1", amount_minor=10, idempotency_key="k")
    fetched = await rp.fetch_refund("pay_1", created.refund_id)
    assert fetched.status == "processed"
