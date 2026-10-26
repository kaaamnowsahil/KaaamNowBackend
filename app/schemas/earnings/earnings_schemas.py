"""Figma "Earnings", "Withdraw", "Add payout method", "Withdrawal successful"."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.earnings.earnings_route_strings import (
    BANK_ACCOUNT_PATTERN,
    IFSC_PATTERN,
    UPI_ID_PATTERN,
)

PayoutAccountType = Literal["upi", "paytm", "bank"]


class LedgerEntry(BaseModel):
    id: UUID
    entry_type: Literal[
        "shift_earning",
        "withdrawal",
        "withdrawal_reversal",
        "commission",
        "cancellation_fee",
        "cancellation_compensation",
        "adjustment",
        "promo_credit",
        "fee_waiver",
    ]
    amount_minor: int
    currency: str
    assignment_id: UUID | None = None
    withdrawal_id: UUID | None = None
    description: str
    created_at: datetime


class LedgerPage(BaseModel):
    items: list[LedgerEntry]
    limit: int
    offset: int


class Reliability(BaseModel):
    """Active strikes and what they lead to (cancellation policy thresholds)."""

    strikes: float
    strikes_to_limit: float = Field(description="Feed is limited from this many strikes.")
    strikes_to_ban: float = Field(description="Account goes on hold from this many strikes.")
    window_days: int = Field(description="Strikes expire after this many days.")
    feed_limited_until: datetime | None = None
    on_hold: bool


class EarningsSummary(BaseModel):
    currency: str
    available_minor: int = Field(description="Withdrawable now. Negative while fees are owed.")
    dues_minor: int = Field(
        default=0, description="Fees owed; recovered from the next earnings before payouts."
    )
    pending_minor: int = Field(description="Approved work awaiting business payment.")
    in_flight_withdrawals_minor: int
    lifetime_minor: int
    this_month_minor: int
    completed_shifts: int
    min_withdrawal_minor: int
    recent: list[LedgerEntry]
    reliability: Reliability | None = None


class PayoutAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: PayoutAccountType
    upi_id: str | None = Field(default=None, pattern=UPI_ID_PATTERN)
    paytm_phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    bank_account_number: str | None = Field(default=None, pattern=BANK_ACCOUNT_PATTERN)
    bank_ifsc: str | None = Field(default=None, pattern=IFSC_PATTERN)
    account_holder_name: str = Field(default="", max_length=120)
    make_default: bool = False


class PayoutAccountPatch(BaseModel):
    """Edit details of a saved account; the type cannot change. Edits clear verification."""

    model_config = ConfigDict(extra="forbid")

    upi_id: str | None = Field(default=None, pattern=UPI_ID_PATTERN)
    paytm_phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    bank_account_number: str | None = Field(default=None, pattern=BANK_ACCOUNT_PATTERN)
    bank_ifsc: str | None = Field(default=None, pattern=IFSC_PATTERN)
    account_holder_name: str | None = Field(default=None, min_length=1, max_length=120)
    make_default: bool | None = None


class PayoutAccountResponse(BaseModel):
    id: UUID
    account_type: PayoutAccountType
    display: str = Field(description="Masked label, e.g. 'UPI · ravi@okaxis' or 'Bank · ••••4321'.")
    upi_id: str | None = None
    paytm_phone: str | None = None
    bank_account_last4: str | None = None
    bank_ifsc: str | None = None
    account_holder_name: str
    is_default: bool
    is_verified: bool = False
    verified_at: datetime | None = None
    created_at: datetime


class WithdrawalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payout_account_id: UUID
    amount_minor: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class WithdrawalResponse(BaseModel):
    id: UUID
    amount_minor: int
    currency: str
    status: Literal["initiated", "processing", "paid", "failed"]
    reference: str
    payout_account_id: UUID
    payout_display: str
    failure_reason: str | None = None
    initiated_at: datetime
    completed_at: datetime | None = None


class WithdrawalPage(BaseModel):
    items: list[WithdrawalResponse]
    limit: int
    offset: int
