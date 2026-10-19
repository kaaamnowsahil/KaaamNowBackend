"""Figma "Final cost", "Pay for this shift", "Scan to pay", "Payment successful", "Payments"."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PaymentMethodCode = Literal["google_pay", "paytm", "apple_pay", "upi_qr", "card_netbanking"]


class InvoiceLine(BaseModel):
    line_kind: Literal["worker_pay", "platform_fee"]
    description: str
    assignment_id: UUID | None = None
    minutes: int | None = None
    rate_minor: int | None = None
    amount_minor: int


class InvoiceResponse(BaseModel):
    id: UUID
    shift_id: UUID
    reference: str
    status: Literal["pending", "paid", "void"]
    currency: str
    job_title: str
    shift_starts_at: datetime
    worker_subtotal_minor: int
    platform_fee_minor: int
    total_minor: int
    fee_percentage: float
    lines: list[InvoiceLine]
    issued_at: datetime
    paid_at: datetime | None = None


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: PaymentMethodCode


class PaymentResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    method: PaymentMethodCode
    provider: str
    status: Literal["pending", "succeeded", "failed", "expired", "cancelled"]
    amount_minor: int
    currency: str
    reference: str
    upi_payload: str | None = Field(default=None, description="Render as QR / open UPI intent.")
    checkout_url: str | None = None
    expires_at: datetime
    paid_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime


class ReceiptResponse(BaseModel):
    payment: PaymentResponse
    invoice: InvoiceResponse
    business_name: str


class PaymentHistoryItem(BaseModel):
    invoice_id: UUID
    invoice_reference: str
    shift_id: UUID
    job_title: str
    shift_starts_at: datetime
    status: Literal["pending", "paid", "void"]
    total_minor: int
    currency: str
    worker_count: int
    paid_at: datetime | None = None
    payment_id: UUID | None = None
    payment_reference: str | None = None
    payment_method: str | None = None


class PaymentHistorySummary(BaseModel):
    paid_this_month_minor: int
    pending_minor: int
    currency: str


class PaymentHistoryPage(BaseModel):
    summary: PaymentHistorySummary
    items: list[PaymentHistoryItem]
    limit: int
    offset: int


class WebhookAck(BaseModel):
    received: bool
    duplicate: bool = False
