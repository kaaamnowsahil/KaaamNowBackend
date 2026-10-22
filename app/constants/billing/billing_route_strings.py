"""Invoice (final cost), payment and receipt route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_BUSINESS, SEGMENT_PAYMENTS

BUSINESS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_BUSINESS}"
PAYMENTS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_PAYMENTS}"
OPENAPI_TAG_BILLING: Final[str] = "billing"
OPENAPI_TAG_WEBHOOKS: Final[str] = "webhooks"

PATH_SHIFT_INVOICE: Final[str] = "/shifts/{shift_id}/invoice"
PATH_INVOICE: Final[str] = "/invoices/{invoice_id}"
PATH_INVOICE_PAYMENTS: Final[str] = "/invoices/{invoice_id}/payments"
PATH_PAYMENTS: Final[str] = "/payments"
PATH_PAYMENT: Final[str] = "/payments/{payment_id}"
PATH_PAYMENT_CONFIRM: Final[str] = "/payments/{payment_id}/confirm"
PATH_WEBHOOK: Final[str] = "/webhooks/{provider}"

HEADER_WEBHOOK_SIGNATURE: Final[str] = "x-kaaamnow-signature"

INVOICE_PENDING: Final[str] = "pending"
INVOICE_PAID: Final[str] = "paid"

PAYMENT_PENDING: Final[str] = "pending"
PAYMENT_SUCCEEDED: Final[str] = "succeeded"
PAYMENT_FAILED: Final[str] = "failed"
PAYMENT_EXPIRED: Final[str] = "expired"
PAYMENT_CANCELLED: Final[str] = "cancelled"

LINE_WORKER_PAY: Final[str] = "worker_pay"
LINE_PLATFORM_FEE: Final[str] = "platform_fee"

MSG_INVOICE_NOT_FOUND: Final[str] = "Invoice not found."
MSG_INVOICE_NOT_READY: Final[str] = "Finish attendance before generating the final cost."
MSG_INVOICE_SHIFT_STATE: Final[str] = "This shift cannot be invoiced yet."
MSG_INVOICE_ALREADY_PAID: Final[str] = "This invoice is already paid."
MSG_INVOICE_NOTHING_DUE: Final[str] = "Nothing is due on this invoice."
MSG_PAYMENT_NOT_FOUND: Final[str] = "Payment not found."
MSG_PAYMENT_NOT_PENDING: Final[str] = "This payment is no longer pending."
MSG_PAYMENT_EXPIRED: Final[str] = "This payment request expired. Start a new payment."
MSG_PAYMENT_METHOD: Final[str] = "Unsupported payment method."
MSG_WEBHOOK_SIGNATURE: Final[str] = "Invalid webhook signature."
MSG_WEBHOOK_DISABLED: Final[str] = "Webhook secret is not configured."
MSG_WEBHOOK_PROVIDER: Final[str] = "Unknown payment provider."
