"""Payment gateway adapters.

``razorpay``: Standard Checkout. We create an order, the app opens Razorpay Checkout with
``checkout_key`` + ``provider_order_id``, then calls verify / confirm; webhooks also settle.
``fake`` simulates a gateway in dev/test: orders are created locally and ``fetch_status``
reports success, so the full pay → settle → earnings flow can be exercised end to end.
In production no money moves through ``fake``, so it reports every payment and refund as
still pending instead.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from app.config.settings import load_settings
from app.constants.application.application_constants import MSG_RAZORPAY_LIVE_KEYS_DISABLED


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


@dataclass(frozen=True)
class ProviderRefund:
    refund_id: str
    status: str  # pending | processed | failed
    failure_reason: str | None = None


class PaymentProvider(Protocol):
    name: str

    async def create_order(
        self, *, reference: str, amount_minor: int, method: str
    ) -> ProviderOrder: ...

    async def fetch_status(self, order_id: str) -> ProviderStatus: ...

    async def refund(
        self, *, provider_payment_id: str, amount_minor: int, idempotency_key: str
    ) -> ProviderRefund: ...

    async def fetch_refund(self, provider_payment_id: str, refund_id: str) -> ProviderRefund: ...


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
            return ProviderOrder(order_id, None, f"https://checkout.fake.kaaamnow/{order_id}")
        payload = upi_intent(
            vpa=settings.upi_payee_vpa,
            payee=settings.upi_payee_name,
            amount_minor=amount_minor,
            reference=reference,
            currency=settings.default_currency,
        )
        return ProviderOrder(order_id, payload, None)

    @staticmethod
    def _simulates_success() -> bool:
        return not load_settings().is_production

    async def fetch_status(self, order_id: str) -> ProviderStatus:
        if not self._simulates_success():
            return ProviderStatus("pending")
        return ProviderStatus("succeeded", f"fake_pay_{secrets.token_hex(8)}")

    async def refund(
        self, *, provider_payment_id: str, amount_minor: int, idempotency_key: str
    ) -> ProviderRefund:
        status = "processed" if self._simulates_success() else "pending"
        return ProviderRefund(f"fake_rfnd_{secrets.token_hex(8)}", status)

    async def fetch_refund(self, provider_payment_id: str, refund_id: str) -> ProviderRefund:
        return ProviderRefund(refund_id, "processed" if self._simulates_success() else "pending")


class PaymentProviderError(RuntimeError):
    pass


_RAZORPAY_REFUND_STATUS = {"processed": "processed", "failed": "failed", "pending": "pending"}


class RazorpayPaymentProvider:
    name = "razorpay"
    _TIMEOUT_SECONDS = 15.0

    def __init__(self) -> None:
        settings = load_settings()
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise PaymentProviderError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set")
        if not settings.razorpay_key_allowed:
            raise PaymentProviderError(MSG_RAZORPAY_LIVE_KEYS_DISABLED)
        self._key_id = settings.razorpay_key_id
        self._key_secret = settings.razorpay_key_secret
        self._base = settings.razorpay_api_base.rstrip("/")
        self._currency = settings.default_currency

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(
            auth=(self._key_id, self._key_secret), timeout=self._TIMEOUT_SECONDS
        ) as client:
            resp = await client.request(method, f"{self._base}{path}", json=json)
        if resp.status_code >= 400:
            error = resp.json().get("error", {}) if resp.content else {}
            raise PaymentProviderError(
                f"Razorpay {method} {path} → {resp.status_code}: "
                f"{error.get('description') or resp.text[:200]}"
            )
        return resp.json()

    async def create_order(
        self, *, reference: str, amount_minor: int, method: str
    ) -> ProviderOrder:
        order = await self._request(
            "POST",
            "/orders",
            {
                "amount": amount_minor,
                "currency": self._currency,
                "receipt": reference[:40],
                "notes": {"reference": reference, "method": method},
            },
        )
        return ProviderOrder(order["id"], None, None)

    async def fetch_status(self, order_id: str) -> ProviderStatus:
        """Captured payment = paid. An authorized one is captured here (auto-capture off)."""
        payments = (await self._request("GET", f"/orders/{order_id}/payments")).get("items", [])
        for payment in payments:
            if payment["status"] == "captured":
                return ProviderStatus("succeeded", payment["id"])
        for payment in payments:
            if payment["status"] == "authorized":
                captured = await self._request(
                    "POST",
                    f"/payments/{payment['id']}/capture",
                    {"amount": payment["amount"], "currency": payment["currency"]},
                )
                if captured.get("status") == "captured":
                    return ProviderStatus("succeeded", payment["id"])
                return ProviderStatus("pending")
        if payments and all(p["status"] == "failed" for p in payments):
            last = payments[0]
            return ProviderStatus(
                "failed", last["id"], (last.get("error_description") or "payment_failed")[:200]
            )
        return ProviderStatus("pending")

    @staticmethod
    def _refund(row: dict) -> ProviderRefund:
        return ProviderRefund(
            row["id"], _RAZORPAY_REFUND_STATUS.get(row.get("status", ""), "pending")
        )

    async def refund(
        self, *, provider_payment_id: str, amount_minor: int, idempotency_key: str
    ) -> ProviderRefund:
        """Reuses an earlier refund carrying the same key (a retry after a timeout must not
        refund twice), otherwise creates one."""
        existing = await self._request("GET", f"/payments/{provider_payment_id}/refunds")
        for row in existing.get("items", []):
            if (row.get("notes") or {}).get("kn_refund_key") == idempotency_key:
                return self._refund(row)
        created = await self._request(
            "POST",
            f"/payments/{provider_payment_id}/refund",
            {
                "amount": amount_minor,
                "speed": "normal",
                "notes": {"kn_refund_key": idempotency_key},
            },
        )
        return self._refund(created)

    async def fetch_refund(self, provider_payment_id: str, refund_id: str) -> ProviderRefund:
        return self._refund(
            await self._request("GET", f"/payments/{provider_payment_id}/refunds/{refund_id}")
        )

    def checkout_signature_valid(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(
            self._key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature.strip())


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    provider = name or load_settings().payment_provider
    if provider == "fake":
        return FakePaymentProvider()
    if provider == "razorpay":
        return RazorpayPaymentProvider()
    raise RuntimeError(f"PAYMENT_PROVIDER={provider!r} is not implemented")
