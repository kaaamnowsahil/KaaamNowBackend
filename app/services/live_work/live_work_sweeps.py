"""Time-based Live Work transitions (run by the background sweep loop)."""

from __future__ import annotations

from datetime import timedelta

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import KIND_EXTENSION_ANSWERED
from app.constants.shifts.shift_route_strings import SHIFT_AWAITING_PAYMENT, SHIFT_CANCELLED
from app.repositories.live_work import live_work_repository
from app.repositories.shifts import assignment_repository, shift_repository
from app.services.live_work import live_refund_service, live_work_billing, live_work_core
from app.services.live_work.live_work_views import cancel_reason
from app.services.notifications.notification_service import notify
from app.services.promos import promo_service
from app.utils.clock import utc_now


async def cancel_unpaid_bookings(pool: asyncpg.Pool) -> int:
    """Posted but never paid within the payment window: close the booking (nothing charged)."""
    now = utc_now()
    cutoff = now - timedelta(seconds=load_settings().live_work_payment_window_seconds)
    changed = 0
    async with pool.acquire() as conn:
        for shift_id in await live_work_repository.list_unpaid_bookings(conn, cutoff):
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                if shift["status"] != SHIFT_AWAITING_PAYMENT:
                    continue
                for invoice in await live_work_repository.list_shift_invoices(conn, shift_id):
                    await live_work_billing.void_invoice(conn, invoice["id"])
                await promo_service.restore_for_booking(conn, shift_id, now)
                await shift_repository.cancel_shift(
                    conn, shift_id, now=now, reason=cancel_reason("system", "payment_not_completed")
                )
                await shift_repository.record_history(
                    conn,
                    shift_id,
                    SHIFT_AWAITING_PAYMENT,
                    SHIFT_CANCELLED,
                    None,
                    "live_work_payment_timeout",
                )
                await live_work_core.notify_cancelled(
                    conn,
                    await live_work_core.business_user_id(conn, shift),
                    "Live Work request closed",
                    f"{shift['job_title']}: payment wasn't completed, so nobody was notified.",
                    {"shift_id": shift_id, "live_work": True},
                )
                changed += 1
    return changed


async def expire_extensions(pool: asyncpg.Pool) -> int:
    settings = load_settings()
    now = utc_now()
    changed = 0
    async with pool.acquire() as conn:
        due = await live_work_repository.list_due_extensions(
            conn,
            now - timedelta(seconds=settings.live_extension_response_seconds),
            now - timedelta(seconds=settings.live_extension_payment_seconds),
        )
        for extension_id in due:
            async with conn.transaction():
                ext = await live_work_repository.lock_extension(conn, extension_id)
                if ext["status"] not in ("requested", "awaiting_payment"):
                    continue
                await live_work_repository.set_extension_status(conn, extension_id, "expired", now)
                if ext["invoice_id"]:
                    await live_work_billing.void_invoice(conn, ext["invoice_id"])
                ctx = await assignment_repository.get_context(conn, ext["assignment_id"])
                await notify(
                    conn,
                    ctx["business_user_id"],
                    KIND_EXTENSION_ANSWERED,
                    "Extension request expired",
                    ctx["job_title"],
                    {
                        "shift_id": ext["shift_id"],
                        "assignment_id": ext["assignment_id"],
                        "live_work": True,
                    },
                )
                changed += 1
    return changed


async def complete_overdue_bookings(pool: asyncpg.Pool) -> int:
    """Reserved (+ extended) time ended and nobody tapped Complete Work: complete it."""
    now = utc_now()
    cutoff = now - timedelta(seconds=load_settings().live_auto_complete_grace_seconds)
    changed = 0
    async with pool.acquire() as conn:
        for shift_id in await live_work_repository.list_overdue_active_bookings(conn, cutoff):
            async with conn.transaction():
                shift = await shift_repository.lock_shift(conn, shift_id)
                current = await live_work_repository.get_current_assignment(conn, shift_id)
                if current is None or shift["ends_at"] >= cutoff:
                    continue
                assignment = await assignment_repository.lock_context(conn, current["id"])
                if assignment["status"] != "checked_in":
                    continue
                pricing = await live_work_repository.get_booking_pricing(conn, shift_id)
                await live_work_core.complete_booking(
                    conn,
                    shift=shift,
                    pricing=pricing,
                    assignment=assignment,
                    ended_by="system",
                    actor_user_id=None,
                    now=now,
                )
                changed += 1
    return changed


async def process_refunds(pool: asyncpg.Pool) -> int:
    return await live_refund_service.process_due_refunds(pool)
