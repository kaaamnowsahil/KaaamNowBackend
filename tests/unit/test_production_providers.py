"""In production, the fake payment / payout providers never report money as moved, and
Razorpay refuses to start without its credentials."""

from __future__ import annotations

import pytest

from app.config.settings import KaaamNowSettings, load_settings
from app.services.billing.sources.payment_provider_factory import FakePaymentProvider
from app.services.earnings.sources.payout_provider_factory import FakePayoutProvider
from app.services.notifications.sources.push_sender_factory import ConsolePushSender


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> KaaamNowSettings:
    monkeypatch.setattr(KaaamNowSettings, "is_production", property(lambda _self: True))
    settings = load_settings()
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 40)
    monkeypatch.setattr(settings, "cors_origin", "https://kaaamnow.in")
    monkeypatch.setattr(settings, "otp_provider", "apitxt")
    return settings


async def test_fake_payments_succeed_outside_production() -> None:
    provider = FakePaymentProvider()
    assert (await provider.fetch_status("fake_order_1")).status == "succeeded"
    refund = await provider.refund(provider_payment_id="p", amount_minor=100, idempotency_key="k")
    assert refund.status == "processed"
    assert (await provider.fetch_refund("p", refund.refund_id)).status == "processed"


async def test_fake_payments_stay_pending_in_production(production) -> None:  # type: ignore[no-untyped-def]
    provider = FakePaymentProvider()
    status = await provider.fetch_status("fake_order_1")
    assert status.status == "pending"
    assert status.provider_payment_id is None
    refund = await provider.refund(provider_payment_id="p", amount_minor=100, idempotency_key="k")
    assert refund.status == "pending"
    assert (await provider.fetch_refund("p", refund.refund_id)).status == "pending"


async def test_fake_payouts_are_paid_only_outside_production(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    provider = FakePayoutProvider()
    payout_id = await provider.create_payout(reference="r", amount_minor=100, account={})
    assert (await provider.fetch_status(payout_id)).status == "paid"
    monkeypatch.setattr(KaaamNowSettings, "is_production", property(lambda _self: True))
    assert (await provider.fetch_status(payout_id)).status == "processing"


async def test_rejected_fake_payout_still_fails_in_production(production) -> None:  # type: ignore[no-untyped-def]
    provider = FakePayoutProvider()
    payout_id = await provider.create_payout(
        reference="r", amount_minor=100, account={"upi_id": "fail@upi"}
    )
    assert (await provider.fetch_status(payout_id)).status == "failed"


def test_razorpay_in_production_needs_keys_and_webhook_secret(production, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(production, "payment_provider", "razorpay")
    monkeypatch.setattr(production, "razorpay_key_id", "rzp_test_unit")
    monkeypatch.setattr(production, "razorpay_key_secret", "")
    monkeypatch.setattr(production, "payment_webhook_secret", " ")
    with pytest.raises(ValueError, match="RAZORPAY_KEY_SECRET, PAYMENT_WEBHOOK_SECRET"):
        production.validate_production_config()


def test_configured_razorpay_passes_production_checks(production, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(production, "payment_provider", "razorpay")
    monkeypatch.setattr(production, "razorpay_key_id", "rzp_test_unit")
    monkeypatch.setattr(production, "razorpay_key_secret", "unit_secret")
    monkeypatch.setattr(production, "payment_webhook_secret", "unit_webhook")
    production.validate_production_config()


def test_console_otp_is_still_refused_in_production(production, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(production, "otp_provider", "console")
    with pytest.raises(ValueError, match="OTP_PROVIDER=console"):
        production.validate_production_config()


async def test_console_push_is_never_reported_sent_in_production(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sender = ConsolePushSender()
    assert (await sender.send(["t"], title="T", body="B", data={"kind": "k"})).delivered == 1
    monkeypatch.setattr(KaaamNowSettings, "is_production", property(lambda _self: True))
    result = await sender.send(["t"], title="T", body="B", data={"kind": "k"})
    assert result.delivered == 0 and not result.retryable
