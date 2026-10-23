"""Start a payment, confirm it (poll / webhook), settle into worker earnings, history."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.billing.billing_route_strings import (
    INVOICE_PAID,
    MSG_INVOICE_ALREADY_PAID,
    MSG_INVOICE_NOTHING_DUE,
    MSG_PAYMENT_NOT_FOUND,
    MSG_PAYMENT_NOT_PENDING,
    MSG_WEBHOOK_DISABLED,
    MSG_WEBHOOK_PROVIDER,
    MSG_WEBHOOK_SIGNATURE,
    PAYMENT_EXPIRED,
    PAYMENT_FAILED,
    PAYMENT_PENDING,
    PAYMENT_SUCCEEDED,
)
from app.constants.notifications.notification_route_strings import (
    KIND_EARNING_CREDITED,
    KIND_PAYMENT_RECEIVED,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import (
    ApiError,
    AuthenticationError,
    bad_request,
    conflict,
    not_found,
)
from app.pagination import clamp_page_limit
from app.repositories.billing import billing_repository
from app.repositories.earnings import earnings_repository
from app.repositories.profiles import profile_repository
from app.schemas.billing.billing_schemas import (
    PaymentCreate,
    PaymentHistoryItem,
    PaymentHistoryPage,
    PaymentHistorySummary,
    PaymentResponse,
    ReceiptResponse,
    WebhookAck,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.billing.invoice_service import build_invoice_response, load_owned_invoice
from app.services.billing.sources.payment_provider_factory import get_payment_provider
from app.services.billing.validation.webhook_signature import signature_matches
from app.services.notifications.notification_service import notify
from app.services.profiles.profile_lookup import business_scope
from app.utils.clock import utc_now
from app.utils.references import PAYMENT_REFERENCE_PREFIX, new_reference


def _payment_response(row: asyncpg.Record) -> PaymentResponse:
    return PaymentResponse.model_validate(dict(row))


def month_bounds(month: str | None, now: datetime) -> tuple[datetime, datetime]:
    """``YYYY-MM`` (UTC) → [start, next month start)."""
    if month:
        try:
            year, mon = (int(part) for part in month.split("-", 1))
            start = datetime(year, mon, 1, tzinfo=UTC)
        except ValueError:
            raise bad_request("invalid_month", "month must be YYYY-MM.") from None
    else:
        start = datetime(now.year, now.month, 1, tzinfo=UTC)
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1, tzinfo=UTC)
    return start, end


async def _load_owned_payment(
    conn: asyncpg.Connection, payment_id: UUID, scope: list[UUID], *, lock: bool
) -> asyncpg.Record:
    row = await (
        billing_repository.lock_payment(conn, payment_id)
        if lock
        else billing_repository.get_payment(conn, payment_id)
    )
    if row is None or row["business_profile_id"] not in scope:
        raise not_found("payment_not_found", MSG_PAYMENT_NOT_FOUND)
    return row


async def start_payment(
    user: AuthenticatedUser, invoice_id: UUID, body: PaymentCreate
) -> PaymentResponse:
    settings = load_settings()
    provider = get_payment_provider()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await load_owned_invoice(conn, invoice_id, await business_scope(conn, user.user_id))
            invoice = await billing_repository.lock_invoice(conn, invoice_id)
            if invoice["status"] == INVOICE_PAID:
                raise conflict("invoice_paid", MSG_INVOICE_ALREADY_PAID)
            if invoice["total_minor"] <= 0:
                raise conflict("nothing_due", MSG_INVOICE_NOTHING_DUE)
            await billing_repository.cancel_pending_payments(conn, invoice_id)
            reference = new_reference(PAYMENT_REFERENCE_PREFIX)
            order = await provider.create_order(
                reference=reference, amount_minor=invoice["total_minor"], method=body.method
            )
            payment_id = await billing_repository.insert_payment(
                conn,
                invoice_id=invoice_id,
                business_profile_id=invoice["business_profile_id"],
                method=body.method,
                provider=provider.name,
                amount_minor=invoice["total_minor"],
                currency=invoice["currency"],
                reference=reference,
                provider_order_id=order.order_id,
                upi_payload=order.upi_payload,
                checkout_url=order.checkout_url,
                expires_at=now + timedelta(seconds=settings.payment_expiry_seconds),
            )
            return _payment_response(await billing_repository.get_payment(conn, payment_id))


async def settle_payment(
    conn: asyncpg.Connection, payment: asyncpg.Record, provider_payment_id: str, now: datetime
) -> None:
    """Mark paid, credit each worker's ledger, notify. Caller holds the payment row lock."""
    if payment["status"] == PAYMENT_SUCCEEDED:
        return
    invoice = await billing_repository.lock_invoice(conn, payment["invoice_id"])
    if invoice["status"] == INVOICE_PAID:
        await billing_repository.mark_payment_failed(
            conn, payment["id"], status=PAYMENT_FAILED, reason="invoice_already_paid"
        )
        return
    await billing_repository.mark_payment_succeeded(
        conn, payment["id"], provider_payment_id=provider_payment_id, now=now
    )
    await billing_repository.mark_invoice_paid(conn, invoice["id"], now)
    credited = await earnings_repository.credit_invoice_earnings(conn, invoice["id"])
    worker_ids = [r["worker_profile_id"] for r in credited]
    await profile_repository.increment_completed_shifts(conn, worker_ids)
    for row in credited:
        worker = await profile_repository.get_worker_profile(conn, row["worker_profile_id"])
        amount = row["amount_minor"]
        await notify(
            conn,
            worker["user_id"],
            KIND_EARNING_CREDITED,
            "Payment received",
            f"₹{amount // 100:,}.{amount % 100:02d} added to your earnings",
            {"invoice_id": invoice["id"], "amount_minor": amount},
        )
    business = await profile_repository.get_business_profile(conn, invoice["business_profile_id"])
    await notify(
        conn,
        business["user_id"],
        KIND_PAYMENT_RECEIVED,
        "Payment successful",
        f"Receipt {payment['reference']}",
        {"payment_id": payment["id"], "invoice_id": invoice["id"]},
    )


async def confirm_payment(user: AuthenticatedUser, payment_id: UUID) -> PaymentResponse:
    """Client returns from UPI / checkout: ask the provider for the final status."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            scope = await business_scope(conn, user.user_id)
            payment = await _load_owned_payment(conn, payment_id, scope, lock=True)
            if payment["status"] == PAYMENT_SUCCEEDED:
                return _payment_response(payment)
            if payment["status"] != PAYMENT_PENDING:
                raise conflict("payment_not_pending", MSG_PAYMENT_NOT_PENDING)
            if payment["expires_at"] <= now:
                await billing_repository.mark_payment_failed(
                    conn, payment_id, status=PAYMENT_EXPIRED, reason="expired"
                )
                return _payment_response(await billing_repository.get_payment(conn, payment_id))
            status = await get_payment_provider(payment["provider"]).fetch_status(
                payment["provider_order_id"]
            )
            if status.status == PAYMENT_SUCCEEDED:
                await settle_payment(conn, payment, status.provider_payment_id or "", now)
            elif status.status == PAYMENT_FAILED:
                await billing_repository.mark_payment_failed(
                    conn, payment_id, status=PAYMENT_FAILED, reason=status.failure_reason or ""
                )
            return _payment_response(await billing_repository.get_payment(conn, payment_id))


async def handle_webhook(provider: str, raw_body: bytes, signature: str | None) -> WebhookAck:
    """Provider push. Body: ``{event_id, event_type, provider_order_id, provider_payment_id,
    status, failure_reason?}`` signed with ``PAYMENT_WEBHOOK_SECRET``."""
    settings = load_settings()
    if provider != settings.payment_provider:
        raise not_found("unknown_provider", MSG_WEBHOOK_PROVIDER)
    if not settings.payment_webhook_secret:
        raise ApiError(503, "webhook_disabled", MSG_WEBHOOK_DISABLED)
    if not signature_matches(settings.payment_webhook_secret, raw_body, signature):
        raise AuthenticationError(MSG_WEBHOOK_SIGNATURE, code="webhook_signature_invalid")
    try:
        payload = json.loads(raw_body)
        event_id = str(payload["event_id"])
        event_type = str(payload.get("event_type", "payment.updated"))
        order_id = str(payload["provider_order_id"])
        status = str(payload["status"])
    except (ValueError, KeyError, TypeError):
        raise bad_request("webhook_payload_invalid", "Malformed webhook payload.") from None
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            event_row_id = await billing_repository.insert_webhook_event(
                conn, provider=provider, event_id=event_id, event_type=event_type, payload=payload
            )
            if event_row_id is None:
                return WebhookAck(received=True, duplicate=True)
            payment = await billing_repository.lock_payment_by_order(conn, provider, order_id)
            if payment is not None and payment["status"] == PAYMENT_PENDING:
                if status == PAYMENT_SUCCEEDED:
                    await settle_payment(
                        conn, payment, str(payload.get("provider_payment_id") or ""), now
                    )
                elif status == PAYMENT_FAILED:
                    await billing_repository.mark_payment_failed(
                        conn,
                        payment["id"],
                        status=PAYMENT_FAILED,
                        reason=str(payload.get("failure_reason") or "")[:200],
                    )
            await billing_repository.mark_webhook_processed(conn, event_row_id, now)
    return WebhookAck(received=True)


async def get_receipt(user: AuthenticatedUser, payment_id: UUID) -> ReceiptResponse:
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id)
        payment = await _load_owned_payment(conn, payment_id, scope, lock=False)
        invoice = await build_invoice_response(conn, payment["invoice_id"])
        business = await profile_repository.get_business_profile(
            conn, payment["business_profile_id"]
        )
    return ReceiptResponse(
        payment=_payment_response(payment),
        invoice=invoice,
        business_name=business["business_name"],
    )


async def get_payment(user: AuthenticatedUser, payment_id: UUID) -> PaymentResponse:
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id)
        return _payment_response(await _load_owned_payment(conn, payment_id, scope, lock=False))


async def history(
    user: AuthenticatedUser,
    *,
    status: str | None,
    month: str | None,
    limit: int | None,
    offset: int,
    business_profile_id: UUID | None = None,
) -> PaymentHistoryPage:
    settings = load_settings()
    now = utc_now()
    page_limit = clamp_page_limit(limit)
    this_month_start, this_month_end = month_bounds(None, now)
    filter_start, filter_end = month_bounds(month, now) if month else (None, None)
    statuses = [status] if status else ["pending", "paid"]
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id, business_profile_id)
        rows = await billing_repository.list_payment_history(
            conn,
            scope,
            statuses=statuses,
            month_start=filter_start,
            month_end=filter_end,
            limit=page_limit,
            offset=offset,
        )
        summary = await billing_repository.payment_history_summary(
            conn, scope, this_month_start, this_month_end
        )
    return PaymentHistoryPage(
        summary=PaymentHistorySummary(
            paid_this_month_minor=summary["paid_this_month_minor"],
            pending_minor=summary["pending_minor"],
            currency=settings.default_currency,
        ),
        items=[PaymentHistoryItem.model_validate(dict(r)) for r in rows],
        limit=page_limit,
        offset=offset,
    )
