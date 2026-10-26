"""Admin booking override and ledger models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OverrideAction = Literal[
    "waive_worker_fee", "void_strike", "unban_worker", "revoke_voucher", "refund_business"
]


class OverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OverrideAction
    reason: str = Field(min_length=5, max_length=500)
    amount_minor: int | None = Field(
        default=None, gt=0, description="Only for refund_business: extra refund to the business."
    )
    support_ticket_id: UUID | None = None


class OverrideView(BaseModel):
    id: UUID
    action: str
    amount_minor: int
    reason: str
    admin_user_id: UUID | None
    support_ticket_id: UUID | None
    created_at: datetime


class LedgerLine(BaseModel):
    """One money / reliability event on the booking, newest first."""

    kind: str
    amount_minor: int
    description: str
    created_at: datetime


class BookingLedger(BaseModel):
    assignment_id: UUID
    shift_id: UUID
    job_title: str
    status: str
    worker_name: str | None
    business_name: str
    currency: str
    invoices: list[LedgerLine]
    charges: list[LedgerLine]
    worker_entries: list[LedgerLine]
    strikes: list[LedgerLine]
    vouchers: list[LedgerLine]
    overrides: list[OverrideView]
