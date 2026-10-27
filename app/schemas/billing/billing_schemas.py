"""Figma "Final cost", "Pay for this shift", "Scan to pay", "Payment successful", "Payments"."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PaymentMethodCode = Literal["google_pay", "paytm", "apple_pay", "upi_qr", "card_netbanking"]


class InvoiceLine(BaseModel):
    line_kind: Literal["worker_pay", "platform_fee", "gateway_fee", "tax"]
    description: str
    assignment_id: UUID | None = None
    minutes: int | None = None
    rate_minor: int | None = None
    amount_minor: int


class InvoiceResponse(BaseModel):
    id: UUID
    shift_id: UUID
    reference: str
    invoice_kind: Literal["deposit", "final", "live_extension"] = Field(
        description=(
            "deposit: paid at posting. final: after the shift; the deposit is applied. "
            "live_extension: approved extra Live Work time."
        )
    )
    status: Literal["pending", "paid", "void"]
    currency: str
    job_title: str
    shift_starts_at: datetime
    worker_subtotal_minor: int
    platform_fee_minor: int = Field(description="Business service fee (commission).")
    gateway_fee_minor: int
    tax_minor: int = Field(default=0, description="Live Work tax; separate from commission.")
    tax_percentage: float = 0
    tax_label: str | None = None
    tax_base: str | None = None
    total_minor: int
    fee_percentage: float
    gateway_fee_percentage: float
    worker_fee_percentage: float
    deposit_applied_minor: int
    amount_due_minor: int = Field(description="What a payment on this invoice charges now.")
    refund_due_minor: int = Field(description="Deposit excess owed back to the business.")
    promo_code: str | None = None
    promo_discount_minor: int = Field(
        default=0, description="Already taken off the service fee / gateway charge above."
    )
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
    provider_order_id: str = Field(description="Razorpay: pass as ``order_id`` to Checkout.")
    checkout_key: str | None = Field(
        default=None, description="Razorpay key id: pass as ``key`` to Checkout."
    )
    expires_at: datetime
    paid_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime


class RazorpayCheckoutResult(BaseModel):
    """Fields Razorpay Checkout passes to its ``handler`` on success."""

    model_config = ConfigDict(extra="forbid")

    razorpay_payment_id: str = Field(max_length=64)
    razorpay_order_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=128)


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
