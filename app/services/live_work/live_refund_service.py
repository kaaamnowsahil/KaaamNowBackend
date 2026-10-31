"""Live Work refunds through the payment gateway.

Refunds are queued inside the business transaction (``queue_refund``) and sent to the provider
after it commits (``process_refund`` / the sweep), so a gateway call never holds row locks and a
rolled-back cancellation never refunds money. Each row has an idempotency key; the Razorpay
adapter reuses a refund already created with that key, so retries never refund twice.
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
import httpx

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.repositories.live_work import live_work_repository
from app.services.billing.sources.payment_provider_factory import (
    PaymentProviderError,
    get_payment_provider,
)
from app.utils.clock import utc_now

logger = logging.getLogger(__name__)

REFUND_BATCH = 20

REASON_NO_WORKERS = "no_workers_found"
REASON_BUSINESS_CANCELLED = "business_cancelled"
REASON_WORKER_LEFT = "worker_left_unworked_time"
REASON_LATE_PAYMENT = "payment_after_booking_closed"
REASON_EXTENSION_VOID = "extension_not_applied"
REASON_UNFILLED_SEATS = "unfilled_seats"
REASON_SEAT_RELEASED = "seat_released"
REASON_UNWORKED_TIME = "finished_early_unworked_time"


async def queue_refund(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    invoice_id: UUID,
    amount_minor: int,
    reason: str,
    actor_user_id: UUID | None,
    assignment_id: UUID | None = None,
    scope: str | None = None,
) -> UUID | None:
    """Queue a refund of ``amount_minor`` from the invoice's successful payment, never more than
    is left unrefunded on it. Idempotent per (reason, payment, seat or ``scope``). Returns the
    refund id, or None when nothing was paid / already queued."""
    if amount_minor <= 0:
        return None
    payment = await live_work_repository.get_succeeded_payment(conn, invoice_id)
    if payment is None or not payment["provider_payment_id"]:
        return None
    left = payment["amount_minor"] - await live_work_repository.payment_refunded_minor(
        conn, payment["id"]
    )
    amount = min(amount_minor, left)
    if amount <= 0:
        return None
    key = f"{reason}:{payment['id']}"
    if assignment_id is not None or scope:
        key += f":{assignment_id or scope}"
    refund_id = await live_work_repository.insert_refund(
        conn,
        shift_id=shift_id,
        payment=payment,
        amount_minor=amount,
        reason=reason,
        idempotency_key=key,
        created_by_user_id=actor_user_id,
        assignment_id=assignment_id,
    )
    if refund_id is not None:
        await live_work_repository.add_refund_due(conn, invoice_id, amount)
    return refund_id


async def _payment_for(conn: asyncpg.Connection, refund: asyncpg.Record) -> asyncpg.Record:
    return await conn.fetchrow("SELECT * FROM payments WHERE id = $1", refund["payment_id"])


async def _attempt(conn: asyncpg.Connection, refund: asyncpg.Record) -> None:
    now = utc_now()
    payment = await _payment_for(conn, refund)
    provider = get_payment_provider(refund["provider"])
    try:
        if refund["provider_refund_id"]:
            result = await provider.fetch_refund(
                payment["provider_payment_id"], refund["provider_refund_id"]
            )
        else:
            result = await provider.refund(
                provider_payment_id=payment["provider_payment_id"],
                amount_minor=refund["amount_minor"],
                idempotency_key=refund["idempotency_key"],
            )
    except (PaymentProviderError, httpx.HTTPError, KeyError) as exc:
        logger.warning("live refund %s failed: %s", refund["id"], exc)
        await live_work_repository.set_refund_result(
            conn,
            refund["id"],
            status="failed",
            provider_refund_id=None,
            failure_reason=str(exc)[:200],
            now=now,
        )
        return
    await live_work_repository.set_refund_result(
        conn,
        refund["id"],
        status=result.status,
        provider_refund_id=result.refund_id,
        failure_reason=result.failure_reason,
        now=now,
    )


async def process_refund(refund_id: UUID) -> None:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            refund = await live_work_repository.lock_refund(conn, refund_id)
            if refund is None or refund["status"] == "processed":
                return
            await _attempt(conn, refund)


async def process_refunds(refund_ids: list[UUID | None]) -> None:
    """Called after the queuing transaction commits; failures stay queued for the sweep."""
    for refund_id in refund_ids:
        if refund_id is None:
            continue
        try:
            await process_refund(refund_id)
        except Exception:
            logger.exception("live refund %s could not be processed now", refund_id)


async def process_due_refunds(pool: asyncpg.Pool) -> int:
    """Sweep: send pending refunds, re-check provider-pending ones, retry failures."""
    max_attempts = load_settings().live_refund_max_attempts
    done = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for refund in await live_work_repository.lock_due_refunds(
                conn, max_attempts, REFUND_BATCH
            ):
                await _attempt(conn, refund)
                done += 1
    return done


async def admin_retry(refund_id: UUID) -> asyncpg.Record:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            refund = await live_work_repository.lock_refund(conn, refund_id)
            if refund is None:
                raise not_found("refund_not_found", "Refund not found.")
            if refund["status"] == "processed":
                raise conflict("refund_processed", "This refund was already processed.")
            await live_work_repository.reset_refund_attempts(conn, refund_id)
            await _attempt(conn, await live_work_repository.lock_refund(conn, refund_id))
            return await live_work_repository.lock_refund(conn, refund_id)
