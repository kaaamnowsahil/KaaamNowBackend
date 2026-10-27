"""Payout rails (RazorpayX / Cashfree Payouts) are an OWNER DECISION.

``fake`` marks payouts paid on the next status poll; a UPI id starting with ``fail`` simulates
a bank rejection so the reversal path can be exercised. In production no money moves through
``fake``, so payouts stay ``processing`` until a real rail settles them.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from app.config.settings import load_settings


@dataclass(frozen=True)
class PayoutStatus:
    status: str  # processing | paid | failed
    failure_reason: str | None = None


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


def get_payout_provider(name: str | None = None) -> PayoutProvider:
    provider = name or load_settings().payout_provider
    if provider == "fake":
        return FakePayoutProvider()
    raise RuntimeError(f"PAYOUT_PROVIDER={provider!r} is not implemented")
