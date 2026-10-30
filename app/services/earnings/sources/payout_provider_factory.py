"""Worker payout rails.

``fake`` marks payouts paid on the next status poll; a UPI id starting with ``fail`` simulates
a bank rejection so the reversal path can be exercised. In production no money moves through
``fake``, so payouts stay ``processing`` until a real rail settles them.

``razorpayx`` sends real RazorpayX payouts (UPI to a VPA, IMPS to a bank account) from
``RAZORPAYX_ACCOUNT_NUMBER`` with the Razorpay key pair. Paytm wallets are not a RazorpayX
fund-account type, so those withdrawals are refused before any money leaves.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config.settings import load_settings
from app.constants.application.application_constants import MSG_RAZORPAY_LIVE_KEYS_DISABLED


@dataclass(frozen=True)
class PayoutStatus:
    status: str  # processing | paid | failed
    failure_reason: str | None = None


class PayoutProviderError(RuntimeError):
    pass


class PayoutProvider(Protocol):
    name: str

    async def create_payout(
        self, *, reference: str, amount_minor: int, account: dict[str, str | None]
    ) -> str:
        """Return the provider payout id."""
        ...

    async def fetch_status(self, provider_payout_id: str) -> PayoutStatus: ...


class FakePayoutProvider:
    name = "fake"

    async def create_payout(
        self, *, reference: str, amount_minor: int, account: dict[str, str | None]
    ) -> str:
        should_fail = (account.get("upi_id") or "").lower().startswith("fail")
        return f"fake_payout_{'fail_' if should_fail else ''}{secrets.token_hex(8)}"

    async def fetch_status(self, provider_payout_id: str) -> PayoutStatus:
        if provider_payout_id.startswith("fake_payout_fail_"):
            return PayoutStatus("failed", "Beneficiary account rejected the transfer")
        if load_settings().is_production:
            return PayoutStatus("processing")
        return PayoutStatus("paid")


_RAZORPAYX_FAILED = frozenset({"failed", "reversed", "rejected", "cancelled"})


class RazorpayXPayoutProvider:
    name = "razorpayx"
    _TIMEOUT_SECONDS = 15.0

    def __init__(self) -> None:
        settings = load_settings()
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise PayoutProviderError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set")
        if not settings.razorpayx_account_number:
            raise PayoutProviderError("RAZORPAYX_ACCOUNT_NUMBER is not set")
        if not settings.razorpay_key_allowed:
            raise PayoutProviderError(MSG_RAZORPAY_LIVE_KEYS_DISABLED)
        self._key_id = settings.razorpay_key_id
        self._key_secret = settings.razorpay_key_secret
        self._base = settings.razorpay_api_base.rstrip("/")
        self._account_number = settings.razorpayx_account_number
        self._currency = settings.default_currency

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        async with httpx.AsyncClient(
            auth=(self._key_id, self._key_secret), timeout=self._TIMEOUT_SECONDS
        ) as client:
            resp = await client.request(method, f"{self._base}{path}", json=json, headers=headers)
        if resp.status_code >= 400:
            error = resp.json().get("error", {}) if resp.content else {}
            raise PayoutProviderError(
                f"RazorpayX {method} {path} → {resp.status_code}: "
                f"{error.get('description') or resp.text[:200]}"
            )
        return resp.json()

    @staticmethod
    def _fund_account(account: dict[str, str | None]) -> tuple[dict, str]:
        holder = (account.get("account_holder_name") or "").strip() or "KaaamNow worker"
        if account.get("account_type") == "upi" and account.get("upi_id"):
            return {"account_type": "vpa", "vpa": {"address": account["upi_id"]}}, "UPI"
        if (
            account.get("account_type") == "bank"
            and account.get("bank_account_number")
            and account.get("bank_ifsc")
        ):
            return {
                "account_type": "bank_account",
                "bank_account": {
                    "name": holder,
                    "ifsc": account["bank_ifsc"],
                    "account_number": account["bank_account_number"],
                },
            }, "IMPS"
        raise PayoutProviderError(
            f"RazorpayX cannot pay a {account.get('account_type')!r} payout account"
        )

    async def create_payout(
        self, *, reference: str, amount_minor: int, account: dict[str, str | None]
    ) -> str:
        fund_account, mode = self._fund_account(account)
        holder = (account.get("account_holder_name") or "").strip() or "KaaamNow worker"
        contact = await self._request(
            "POST",
            "/contacts",
            {"name": holder[:50], "type": "employee", "reference_id": reference[:40]},
        )
        fund = await self._request(
            "POST", "/fund_accounts", {"contact_id": contact["id"], **fund_account}
        )
        payout = await self._request(
            "POST",
            "/payouts",
            {
                "account_number": self._account_number,
                "fund_account_id": fund["id"],
                "amount": amount_minor,
                "currency": self._currency,
                "mode": mode,
                "purpose": "payout",
                "queue_if_low_balance": True,
                "reference_id": reference[:40],
                "narration": "KaaamNow payout",
            },
            headers={"X-Payout-Idempotency": reference},
        )
        return payout["id"]

    async def fetch_status(self, provider_payout_id: str) -> PayoutStatus:
        payout = await self._request("GET", f"/payouts/{provider_payout_id}")
        status = payout.get("status")
        if status == "processed":
            return PayoutStatus("paid")
        if status in _RAZORPAYX_FAILED:
            details = payout.get("status_details") or {}
            reason = details.get("description") or payout.get("failure_reason")
            return PayoutStatus("failed", reason or f"Payout {status}")
        return PayoutStatus("processing")


def get_payout_provider(name: str | None = None) -> PayoutProvider:
    provider = name or load_settings().payout_provider
    if provider == "fake":
        return FakePayoutProvider()
    if provider == "razorpayx":
        return RazorpayXPayoutProvider()
    raise RuntimeError(f"PAYOUT_PROVIDER={provider!r} is not implemented")
