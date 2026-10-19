"""asyncpg persistence for invoices, payments and webhook events."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.repositories.billing.billing_queries import (
    CANCEL_PENDING_PAYMENTS,
    EXPIRE_DUE_PAYMENTS,
    GET_INVOICE,
    GET_INVOICE_BY_SHIFT,
    GET_PAYMENT,
    INSERT_INVOICE,
    INSERT_INVOICE_LINE,
    INSERT_PAYMENT,
    INSERT_WEBHOOK_EVENT,
    LIST_INVOICE_LINES,
    LIST_PAYMENT_HISTORY,
    LOCK_INVOICE,
    LOCK_PAYMENT,
    LOCK_PAYMENT_BY_ORDER,
    MARK_INVOICE_PAID,
    MARK_PAYMENT_FAILED,
    MARK_PAYMENT_SUCCEEDED,
    MARK_WEBHOOK_PROCESSED,
    PAYMENT_HISTORY_SUMMARY,
)


async def insert_invoice(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    business_profile_id: UUID,
    reference: str,
    status: str,
    currency: str,
    worker_subtotal_minor: int,
    platform_fee_minor: int,
    fee_percentage: Decimal,
    fee_policy_version: int,
    now: datetime,
) -> UUID:
    return await conn.fetchval(
        INSERT_INVOICE,
        shift_id,
        business_profile_id,
        reference,
        status,
        currency,
        worker_subtotal_minor,
        platform_fee_minor,
        worker_subtotal_minor + platform_fee_minor,
        fee_percentage,
        fee_policy_version,
        now,
        now if status == "paid" else None,
    )


async def insert_invoice_line(
    conn: asyncpg.Connection,
    invoice_id: UUID,
    *,
    assignment_id: UUID | None,
    line_kind: str,
    description: str,
    minutes: int | None,
    rate_minor: int | None,
    amount_minor: int,
    sort_order: int,
) -> None:
    await conn.execute(
        INSERT_INVOICE_LINE,
        invoice_id,
        assignment_id,
        line_kind,
        description,
        minutes,
        rate_minor,
        amount_minor,
        sort_order,
    )


async def get_invoice(conn: asyncpg.Connection, invoice_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_INVOICE, invoice_id)


async def get_invoice_by_shift(conn: asyncpg.Connection, shift_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_INVOICE_BY_SHIFT, shift_id)


async def lock_invoice(conn: asyncpg.Connection, invoice_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_INVOICE, invoice_id)


async def list_invoice_lines(conn: asyncpg.Connection, invoice_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_INVOICE_LINES, invoice_id)


async def mark_invoice_paid(conn: asyncpg.Connection, invoice_id: UUID, now: datetime) -> None:
    await conn.execute(MARK_INVOICE_PAID, invoice_id, now)


async def insert_payment(
    conn: asyncpg.Connection,
    *,
    invoice_id: UUID,
    business_profile_id: UUID,
    method: str,
    provider: str,
    amount_minor: int,
    currency: str,
    reference: str,
    provider_order_id: str,
    upi_payload: str | None,
    checkout_url: str | None,
    expires_at: datetime,
) -> UUID:
    return await conn.fetchval(
        INSERT_PAYMENT,
        invoice_id,
        business_profile_id,
        method,
        provider,
        amount_minor,
        currency,
        reference,
        provider_order_id,
        upi_payload,
        checkout_url,
        expires_at,
    )


async def get_payment(conn: asyncpg.Connection, payment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_PAYMENT, payment_id)


async def lock_payment(conn: asyncpg.Connection, payment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_PAYMENT, payment_id)


async def lock_payment_by_order(
    conn: asyncpg.Connection, provider: str, provider_order_id: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_PAYMENT_BY_ORDER, provider, provider_order_id)


async def cancel_pending_payments(conn: asyncpg.Connection, invoice_id: UUID) -> None:
    await conn.execute(CANCEL_PENDING_PAYMENTS, invoice_id)


async def mark_payment_succeeded(
    conn: asyncpg.Connection, payment_id: UUID, *, provider_payment_id: str, now: datetime
) -> None:
    await conn.execute(MARK_PAYMENT_SUCCEEDED, payment_id, provider_payment_id, now)


async def mark_payment_failed(
    conn: asyncpg.Connection, payment_id: UUID, *, status: str, reason: str
) -> None:
    await conn.execute(MARK_PAYMENT_FAILED, payment_id, status, reason)


async def expire_due_payments(conn: asyncpg.Connection, now: datetime) -> int:
    return int((await conn.execute(EXPIRE_DUE_PAYMENTS, now)).split()[-1])


async def insert_webhook_event(
    conn: asyncpg.Connection,
    *,
    provider: str,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> UUID | None:
    return await conn.fetchval(INSERT_WEBHOOK_EVENT, provider, event_id, event_type, payload)


async def mark_webhook_processed(
    conn: asyncpg.Connection, event_row_id: UUID, now: datetime
) -> None:
    await conn.execute(MARK_WEBHOOK_PROCESSED, event_row_id, now)


async def list_payment_history(
    conn: asyncpg.Connection,
    business_profile_id: UUID,
    *,
    statuses: list[str],
    month_start: datetime | None,
    month_end: datetime | None,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        LIST_PAYMENT_HISTORY, business_profile_id, statuses, month_start, month_end, limit, offset
    )


async def payment_history_summary(
    conn: asyncpg.Connection, business_profile_id: UUID, month_start: datetime, month_end: datetime
) -> asyncpg.Record:
    return await conn.fetchrow(PAYMENT_HISTORY_SUMMARY, business_profile_id, month_start, month_end)
