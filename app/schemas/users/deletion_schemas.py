"""Account deletion request, review and retention schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DeletionStatus = Literal["pending", "approved", "on_hold", "completed"]
DeletionHoldBasis = Literal[
    "pending_booking",
    "pending_payment",
    "refund",
    "dispute",
    "complaint",
    "legal_obligation",
    "fraud_investigation",
]


class DeletionHold(BaseModel):
    id: UUID
    basis: DeletionHoldBasis
    reason: str
    reference: str | None = None
    expires_at: datetime


class AccountDeletionRequestResponse(BaseModel):
    id: UUID
    status: DeletionStatus
    requested_at: datetime
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    blockers: list[str] = Field(default_factory=list)
    holds: list[DeletionHold] = Field(default_factory=list)


class AccountDeletionHoldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: DeletionHoldBasis
    reason: str = Field(min_length=20, max_length=1000)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    expires_at: datetime


class AdminAccountDeletionRequest(AccountDeletionRequestResponse):
    user_id: UUID
    phone: str
    full_name: str
    roles: list[str]


class AccountDeletionEvent(BaseModel):
    event_type: str
    actor_user_id: UUID | None = None
    details: dict[str, object]
    created_at: datetime


class AdminAccountDeletionRequestDetail(AdminAccountDeletionRequest):
    events: list[AccountDeletionEvent] = Field(default_factory=list)


class AccountDeletionRequestPage(BaseModel):
    items: list[AdminAccountDeletionRequest]
    total: int
    limit: int
    offset: int
