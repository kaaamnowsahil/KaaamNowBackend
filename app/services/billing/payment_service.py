"""Start a payment, confirm it (poll / webhook), settle into worker earnings, history."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx

from app.config.settings import load_settings
from app.constants.billing.billing_route_strings import (
    HEADER_RAZORPAY_EVENT_ID,
    HEADER_RAZORPAY_SIGNATURE,
    HEADER_WEBHOOK_SIGNATURE,
    INVOICE_KIND_DEPOSIT,
    INVOICE_PAID,
    MSG_INVOICE_ALREADY_PAID,
    MSG_INVOICE_NOTHING_DUE,
    MSG_PAYMENT_MISMATCH,
    MSG_PAYMENT_NOT_FOUND,
    MSG_PAYMENT_NOT_PENDING,
    MSG_PAYMENT_PROVIDER_ERROR,
    MSG_PAYMENT_SIGNATURE,
    MSG_WEBHOOK_DISABLED,
    MSG_WEBHOOK_PROVIDER,
    MSG_WEBHOOK_SIGNATURE,
    PAYMENT_CANCELLED,
    PAYMENT_EXPIRED,
    PAYMENT_FAILED,
    PAYMENT_PENDING,
    PAYMENT_SUCCEEDED,
    PROVIDER_FAKE,
    PROVIDER_RAZORPAY,
)
from app.constants.notifications.notification_route_strings import KIND_PAYMENT_RECEIVED
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
from app.repositories.profiles import profile_repository
from app.schemas.billing.billing_schemas import (
    PaymentCreate,
    PaymentHistoryItem,
    PaymentHistoryPage,
    PaymentHistorySummary,
    PaymentResponse,
    RazorpayCheckoutResult,
    ReceiptResponse,
    WebhookAck,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.billing.invoice_service import build_invoice_response, load_owned_invoice
from app.services.billing.settlement import release_invoice_earnings
from app.services.billing.sources.payment_provider_factory import (
    PaymentProvider,
    PaymentProviderError,
    ProviderOrder,
    RazorpayPaymentProvider,
    get_payment_provider,
)
from app.services.billing.validation.webhook_signature import signature_matches
from app.services.notifications.notification_service import notify
from app.services.profiles.profile_lookup import business_scope
from app.services.shifts import shift_service
from app.utils.clock import utc_now
from app.utils.references import PAYMENT_REFERENCE_PREFIX, new_reference

logger = logging.getLogger(__name__)

_RAZORPAY_EVENT_STATUS = {
    "payment.captured": PAYMENT_SUCCEEDED,
    "order.paid": PAYMENT_SUCCEEDED,
    "payment.failed": PAYMENT_FAILED,
}


_SETTLEABLE_STATUSES = (PAYMENT_PENDING, PAYMENT_EXPIRED, PAYMENT_CANCELLED)


def _payment_response(row: asyncpg.Record) -> PaymentResponse:
    data = dict(row)
    if row["provider"] == PROVIDER_RAZORPAY:
        data["checkout_key"] = load_settings().razorpay_key_id
    return PaymentResponse.model_validate(data)


async def _create_order(
    provider: PaymentProvider, *, reference: str, amount_minor: int, method: str
) -> ProviderOrder:
    try:
        return await provider.create_order(
            reference=reference, amount_minor=amount_minor, method=method
        )
    except (PaymentProviderError, httpx.HTTPError) as exc:
        logger.warning("payment order failed: %s", exc)
        raise ApiError(502, "payment_provider_error", MSG_PAYMENT_PROVIDER_ERROR) from None


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
            amount_due = invoice["total_minor"] - invoice["deposit_applied_minor"]
            if amount_due <= 0:
                raise conflict("nothing_due", MSG_INVOICE_NOTHING_DUE)
            await billing_repository.cancel_pending_payments(conn, invoice_id)
            reference = new_reference(PAYMENT_REFERENCE_PREFIX)
            order = await _create_order(
                provider, reference=reference, amount_minor=amount_due, method=body.method
            )
            payment_id = await billing_repository.insert_payment(
                conn,
                invoice_id=invoice_id,
                business_profile_id=invoice["business_profile_id"],
                method=body.method,
                provider=provider.name,
                amount_minor=amount_due,
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
    """Mark paid, then publish the shift (deposit) or release worker earnings (final).
    Caller holds the payment row lock."""
    if payment["status"] == PAYMENT_SUCCEEDED:
        return
    invoice = await billing_repository.lock_invoice(conn, payment["invoice_id"])
    if invoice["status"] == INVOICE_PAID and payment["status"] != PAYMENT_PENDING:
        logger.error(
            "late payment %s on paid invoice %s needs a manual refund",
            payment["id"],
            invoice["id"],
        )
    if invoice["status"] == INVOICE_PAID:
        await billing_repository.mark_payment_failed(
            conn, payment["id"], status=PAYMENT_FAILED, reason="invoice_already_paid"
        )
        return
    await billing_repository.mark_payment_succeeded(
        conn, payment["id"], provider_payment_id=provider_payment_id, now=now
    )
    await billing_repository.mark_invoice_paid(conn, invoice["id"], now)
    if invoice["invoice_kind"] == INVOICE_KIND_DEPOSIT:
        await shift_service.activate_paid_shift(conn, invoice["shift_id"], now)
    else:
        await release_invoice_earnings(conn, invoice["id"])
    business = await profile_repository.get_business_profile(conn, invoice["business_profile_id"])
    await notify(
        conn,
        business["user_id"],
        KIND_PAYMENT_RECEIVED,
        "Payment successful",
        f"Receipt {payment['reference']}",
        {"payment_id": payment["id"], "invoice_id": invoice["id"]},
    )


async def _confirm_locked(
    conn: asyncpg.Connection, payment: asyncpg.Record, now: datetime
) -> PaymentResponse:
    """Ask the provider for the final status. A real gateway may report success after our
    local expiry (money already taken), so expired / cancelled payments still settle."""
    payment_id = payment["id"]
    if payment["status"] == PAYMENT_SUCCEEDED:
        return _payment_response(payment)
    is_fake = payment["provider"] == PROVIDER_FAKE
    if payment["status"] != PAYMENT_PENDING and (
        is_fake or payment["status"] not in _SETTLEABLE_STATUSES
    ):
        raise conflict("payment_not_pending", MSG_PAYMENT_NOT_PENDING)
    if is_fake and payment["expires_at"] <= now:
        await billing_repository.mark_payment_failed(
            conn, payment_id, status=PAYMENT_EXPIRED, reason="expired"
        )
        return _payment_response(await billing_repository.get_payment(conn, payment_id))
    try:
        status = await get_payment_provider(payment["provider"]).fetch_status(
            payment["provider_order_id"]
        )
    except (PaymentProviderError, httpx.HTTPError) as exc:
        logger.warning("payment status check failed: %s", exc)
        raise ApiError(502, "payment_provider_error", MSG_PAYMENT_PROVIDER_ERROR) from None
    if status.status == PAYMENT_SUCCEEDED:
        await settle_payment(conn, payment, status.provider_payment_id or "", now)
    elif status.status == PAYMENT_FAILED and payment["status"] == PAYMENT_PENDING:
        await billing_repository.mark_payment_failed(
            conn, payment_id, status=PAYMENT_FAILED, reason=status.failure_reason or ""
        )
    elif payment["expires_at"] <= now and payment["status"] == PAYMENT_PENDING:
        await billing_repository.mark_payment_failed(
            conn, payment_id, status=PAYMENT_EXPIRED, reason="expired"
        )
    return _payment_response(await billing_repository.get_payment(conn, payment_id))


async def confirm_payment(user: AuthenticatedUser, payment_id: UUID) -> PaymentResponse:
    """Client returns from UPI / checkout: ask the provider for the final status."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            scope = await business_scope(conn, user.user_id)
            payment = await _load_owned_payment(conn, payment_id, scope, lock=True)
            return await _confirm_locked(conn, payment, now)


async def verify_razorpay_checkout(
    user: AuthenticatedUser, payment_id: UUID, body: RazorpayCheckoutResult
) -> PaymentResponse:
    """Razorpay Checkout ``handler`` result: check its signature, then confirm."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            scope = await business_scope(conn, user.user_id)
            payment = await _load_owned_payment(conn, payment_id, scope, lock=True)
            provider = get_payment_provider(payment["provider"])
            if not isinstance(provider, RazorpayPaymentProvider) or (
                body.razorpay_order_id != payment["provider_order_id"]
            ):
                raise bad_request("payment_mismatch", MSG_PAYMENT_MISMATCH)
            if not provider.checkout_signature_valid(
                body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
            ):
                raise bad_request("payment_signature_invalid", MSG_PAYMENT_SIGNATURE)
            return await _confirm_locked(conn, payment, now)


def _parse_webhook(
    provider: str, payload: dict, headers: Mapping[str, str]
) -> tuple[str, str, str | None, str, str | None, str]:
    """→ (event_id, event_type, order_id, status, provider_payment_id, failure_reason)."""
    if provider == PROVIDER_RAZORPAY:
        event_type = str(payload["event"])
        entity = payload["payload"]["payment"]["entity"]
        status = _RAZORPAY_EVENT_STATUS.get(event_type, "")
        event_id = headers.get(HEADER_RAZORPAY_EVENT_ID) or f"{event_type}:{entity['id']}"
        return (
            event_id,
            event_type,
            entity.get("order_id"),
            status,
            entity["id"],
            str(entity.get("error_description") or ""),
        )
    return (
        str(payload["event_id"]),
        str(payload.get("event_type", "payment.updated")),
        str(payload["provider_order_id"]),
        str(payload["status"]),
        str(payload.get("provider_payment_id") or ""),
        str(payload.get("failure_reason") or ""),
    )


async def handle_webhook(provider: str, raw_body: bytes, headers: Mapping[str, str]) -> WebhookAck:
    """Provider push signed with ``PAYMENT_WEBHOOK_SECRET`` (HMAC-SHA256 of the raw body).
    Fake body: ``{event_id, event_type, provider_order_id, provider_payment_id, status,
    failure_reason?}``. Razorpay: ``payment.captured`` / ``order.paid`` / ``payment.failed``."""
    settings = load_settings()
    if provider != settings.payment_provider:
        raise not_found("unknown_provider", MSG_WEBHOOK_PROVIDER)
    if not settings.payment_webhook_secret:
        raise ApiError(503, "webhook_disabled", MSG_WEBHOOK_DISABLED)
    signature_header = (
        HEADER_RAZORPAY_SIGNATURE if provider == PROVIDER_RAZORPAY else HEADER_WEBHOOK_SIGNATURE
    )
    if not signature_matches(
        settings.payment_webhook_secret, raw_body, headers.get(signature_header)
    ):
        raise AuthenticationError(MSG_WEBHOOK_SIGNATURE, code="webhook_signature_invalid")
    try:
        payload = json.loads(raw_body)
        event_id, event_type, order_id, status, provider_payment_id, failure_reason = (
            _parse_webhook(provider, payload, headers)
        )
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
            payment = (
                await billing_repository.lock_payment_by_order(conn, provider, order_id)
                if order_id
                else None
            )
            settleable = (PAYMENT_PENDING,) if provider == PROVIDER_FAKE else _SETTLEABLE_STATUSES
            if payment is not None and payment["status"] in settleable:
                if status == PAYMENT_SUCCEEDED:
                    await settle_payment(conn, payment, provider_payment_id or "", now)
                elif status == PAYMENT_FAILED and payment["status"] == PAYMENT_PENDING:
                    await billing_repository.mark_payment_failed(
                        conn, payment["id"], status=PAYMENT_FAILED, reason=failure_reason[:200]
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
