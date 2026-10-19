"""Business: final cost, pay, receipts, payment history. Provider webhook."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from app.constants.application.application_common import (
    SWAGGER_ROLE_BUSINESS,
    SWAGGER_ROLE_PUBLIC,
    swagger_summary,
)
from app.constants.billing.billing_route_strings import (
    BUSINESS_ROUTE_PREFIX,
    HEADER_WEBHOOK_SIGNATURE,
    OPENAPI_TAG_BILLING,
    OPENAPI_TAG_WEBHOOKS,
    PATH_INVOICE,
    PATH_INVOICE_PAYMENTS,
    PATH_PAYMENT,
    PATH_PAYMENT_CONFIRM,
    PATH_PAYMENTS,
    PATH_SHIFT_INVOICE,
    PATH_WEBHOOK,
    PAYMENTS_ROUTE_PREFIX,
)
from app.dependencies import RequireBillingRead, RequireBillingWrite
from app.schemas.billing.billing_schemas import (
    InvoiceResponse,
    PaymentCreate,
    PaymentHistoryPage,
    PaymentResponse,
    ReceiptResponse,
    WebhookAck,
)
from app.services.billing import invoice_service, payment_service

router = APIRouter(prefix=BUSINESS_ROUTE_PREFIX, tags=[OPENAPI_TAG_BILLING])
webhook_router = APIRouter(prefix=PAYMENTS_ROUTE_PREFIX, tags=[OPENAPI_TAG_WEBHOOKS])


@router.post(
    PATH_SHIFT_INVOICE,
    response_model=InvoiceResponse,
    summary=swagger_summary("Generate final cost", SWAGGER_ROLE_BUSINESS),
)
async def generate_invoice(shift_id: UUID, user: RequireBillingWrite) -> InvoiceResponse:
    return await invoice_service.generate_invoice(user, shift_id)


@router.get(
    PATH_SHIFT_INVOICE,
    response_model=InvoiceResponse,
    summary=swagger_summary("Get shift final cost", SWAGGER_ROLE_BUSINESS),
)
async def get_shift_invoice(shift_id: UUID, user: RequireBillingRead) -> InvoiceResponse:
    return await invoice_service.get_shift_invoice(user, shift_id)


@router.get(
    PATH_INVOICE,
    response_model=InvoiceResponse,
    summary=swagger_summary("Get invoice", SWAGGER_ROLE_BUSINESS),
)
async def get_invoice(invoice_id: UUID, user: RequireBillingRead) -> InvoiceResponse:
    return await invoice_service.get_invoice(user, invoice_id)


@router.post(
    PATH_INVOICE_PAYMENTS,
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Start payment (UPI / QR / card)", SWAGGER_ROLE_BUSINESS),
)
async def start_payment(
    invoice_id: UUID, body: PaymentCreate, user: RequireBillingWrite
) -> PaymentResponse:
    return await payment_service.start_payment(user, invoice_id, body)


@router.get(
    PATH_PAYMENTS,
    response_model=PaymentHistoryPage,
    summary=swagger_summary("Payment history", SWAGGER_ROLE_BUSINESS),
)
async def history(
    user: RequireBillingRead,
    status_filter: Literal["pending", "paid"] | None = Query(default=None, alias="status"),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> PaymentHistoryPage:
    return await payment_service.history(
        user, status=status_filter, month=month, limit=limit, offset=offset
    )


@router.get(
    PATH_PAYMENT,
    response_model=ReceiptResponse,
    summary=swagger_summary("Payment receipt", SWAGGER_ROLE_BUSINESS),
)
async def receipt(payment_id: UUID, user: RequireBillingRead) -> ReceiptResponse:
    return await payment_service.get_receipt(user, payment_id)


@router.post(
    PATH_PAYMENT_CONFIRM,
    response_model=PaymentResponse,
    summary=swagger_summary("Confirm payment status", SWAGGER_ROLE_BUSINESS),
)
async def confirm(payment_id: UUID, user: RequireBillingWrite) -> PaymentResponse:
    return await payment_service.confirm_payment(user, payment_id)


@webhook_router.post(
    PATH_WEBHOOK,
    response_model=WebhookAck,
    summary=swagger_summary("Payment provider webhook", SWAGGER_ROLE_PUBLIC),
)
async def webhook(provider: str, request: Request) -> WebhookAck:
    body = await request.body()
    return await payment_service.handle_webhook(
        provider, body, request.headers.get(HEADER_WEBHOOK_SIGNATURE)
    )
