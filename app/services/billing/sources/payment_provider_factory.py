"""Payment gateway adapters. Real gateway (Razorpay / Cashfree / PhonePe) is an OWNER DECISION.

``fake`` simulates a gateway in dev/test: orders are created locally and ``fetch_status``
reports success, so the full pay → settle → earnings flow can be exercised end to end.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from app.config.settings import load_settings


@dataclass(frozen=True)
class ProviderOrder:
    order_id: str
    upi_payload: str | None
    checkout_url: str | None


@dataclass(frozen=True)
class ProviderStatus:
    status: str  # pending | succeeded | failed
    provider_payment_id: str | None = None
    failure_reason: str | None = None


class PaymentProvider(Protocol):
    name: str

    async def create_order(
        self, *, reference: str, amount_minor: int, method: str
    ) -> ProviderOrder: ...

    async def fetch_status(self, order_id: str) -> ProviderStatus: ...


def upi_intent(*, vpa: str, payee: str, amount_minor: int, reference: str, currency: str) -> str:
    amount = f"{amount_minor // 100}.{amount_minor % 100:02d}"
    return (
        f"upi://pay?pa={quote(vpa)}&pn={quote(payee)}&am={amount}"
        f"&tn={quote(reference)}&tr={quote(reference)}&cu={currency}"
    )


class FakePaymentProvider:
    name = "fake"

    async def create_order(
        self, *, reference: str, amount_minor: int, method: str
    ) -> ProviderOrder:
        settings = load_settings()
        order_id = f"fake_order_{secrets.token_hex(8)}"
        if method == "card_netbanking":
            return ProviderOrder(order_id, None, f"https://checkout.fake.kaamnow/{order_id}")
        payload = upi_intent(
            vpa=settings.upi_payee_vpa,
            payee=settings.upi_payee_name,
            amount_minor=amount_minor,
            reference=reference,
            currency=settings.default_currency,
        )
        return ProviderOrder(order_id, payload, None)

    async def fetch_status(self, order_id: str) -> ProviderStatus:
        return ProviderStatus("succeeded", f"fake_pay_{secrets.token_hex(8)}")


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    provider = name or load_settings().payment_provider
    if provider == "fake":
        return FakePaymentProvider()
    raise RuntimeError(f"PAYMENT_PROVIDER={provider!r} is not implemented")
