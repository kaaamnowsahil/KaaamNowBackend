"""Entry points from shared Live / billing code. Each is a no-op for anything that is not a
Live Work booking, so legacy live shifts and scheduled Shifts behave exactly as before."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.notifications.notification_route_strings import (
    KIND_LIVE_EXPIRED,
    KIND_LIVE_FILLED,
    KIND_LIVE_REQUEST,
)
from app.constants.shifts.shift_route_strings import SHIFT_AWAITING_PAYMENT
from app.exceptions.api_errors import conflict
from app.repositories.live_work import live_work_repository
from app.repositories.shifts import shift_repository
from app.services.live_work import live_refund_service, live_work_billing, live_work_core
from app.services.notifications.notification_service import notify
from app.services.promos import promo_service
from app.utils.clock import utc_now
from app.utils.references import CHECK_IN_CODE_ALPHABET

ARRIVAL_CODE_LENGTH = 6
MSG_USE_LIVE_WORK = "This is a Live Work booking. Use the Live Work screen for this action."


def new_arrival_code() -> str:
    return "".join(secrets.choice(CHECK_IN_CODE_ALPHABET) for _ in range(ARRIVAL_CODE_LENGTH))


async def reject_generic_action(conn: asyncpg.Connection, shift_id: UUID) -> None:
    if await live_work_repository.is_live_work(conn, shift_id):
        raise conflict("live_work_action_required", MSG_USE_LIVE_WORK)


async def on_accepted(
    conn: asyncpg.Connection, shift: asyncpg.Record, assignment_id: UUID, now: datetime
) -> None:
    if not await live_work_repository.is_live_work(conn, shift["id"]):
        return
    await live_work_repository.insert_arrival_code(
        conn,
        assignment_id=assignment_id,
        shift_id=shift["id"],
        code=new_arrival_code(),
        expires_at=now + timedelta(seconds=load_settings().live_arrival_code_ttl_seconds),
    )


async def on_search_expired(
    conn: asyncpg.Connection, shift: asyncpg.Record, business_user_id: UUID
) -> bool:
    """No Worker accepted in time: full refund of everything paid. True = handled."""
    if not await live_work_repository.is_live_work(conn, shift["id"]):
        return False
    paid = await live_work_core.unrefunded_total(conn, shift["id"])
    await live_work_core.queue_split_refund(
        conn, shift["id"], paid, live_refund_service.REASON_NO_WORKERS, None
    )
    await promo_service.restore_for_booking(conn, shift["id"], utc_now())
    await notify(
        conn,
        business_user_id,
        KIND_LIVE_EXPIRED,
        "No Workers available right now",
        f"{shift['job_title']}: your full payment is being refunded. You can post again.",
        {"shift_id": shift["id"], "live_work": True},
    )
    return True


async def on_search_partial(
    conn: asyncpg.Connection, shift: asyncpg.Record, seats: int, business_user_id: UUID
) -> bool:
    """Search ended with some seats empty: refund the empty seats' share of the deposit and keep
    the booking for the Workers found. The coupon stays used. True = handled."""
    if not await live_work_repository.is_live_work(conn, shift["id"]):
        return False
    pricing = await live_work_repository.get_booking_pricing(conn, shift["id"])
    missing = max(shift["workers_required"] - seats, 0)
    refund = missing * pricing["total_minor"]
    if refund:
        await live_work_core.queue_split_refund(
            conn,
            shift["id"],
            refund,
            live_refund_service.REASON_UNFILLED_SEATS,
            None,
            deposit_only=True,
            scope=f"search:{shift['search_expires_at'].isoformat()}",
        )
    await live_work_repository.set_shift_workers_required(conn, shift["id"], max(seats, 1))
    worker_word = "Worker" if missing == 1 else "Workers"
    await notify(
        conn,
        business_user_id,
        KIND_LIVE_FILLED,
        f"{seats} of {pricing['workers_required']} Workers found",
        f"{shift['job_title']}: {live_work_billing.rupees(refund)} refunded for "
        f"{missing} {worker_word}.",
        {"shift_id": shift["id"], "live_work": True},
    )
    return True


async def on_filled(conn: asyncpg.Connection, shift_id: UUID, now: datetime) -> None:
    """Seats taken: a Worker may already be working (several-Worker search), so settle."""
    if await live_work_repository.is_live_work(conn, shift_id):
        await live_work_core.settle_status(conn, shift_id, now, None, "live_work_filled")


async def on_deposit_paid(conn: asyncpg.Connection, invoice: asyncpg.Record, now: datetime) -> bool:
    """Reserved amount paid: publish to eligible Workers. A payment that lands after the booking
    closed (cancelled / unpaid timeout) is refunded in full. True = handled."""
    shift_id = invoice["shift_id"]
    if not await live_work_repository.is_live_work(conn, shift_id):
        return False
    shift = await shift_repository.lock_shift(conn, shift_id)
    if shift["status"] != SHIFT_AWAITING_PAYMENT:
        await live_refund_service.queue_refund(
            conn,
            shift_id=shift_id,
            invoice_id=invoice["id"],
            amount_minor=invoice["total_minor"],
            reason=live_refund_service.REASON_LATE_PAYMENT,
            actor_user_id=None,
        )
        return True
    pricing = await live_work_repository.get_booking_pricing(conn, shift_id)
    await promo_service.mark_shift_applied(
        conn,
        shift_id,
        pricing["promo_discount_minor"] * live_work_billing.seats(pricing),
        now,
    )
    await live_work_core.restart_search(conn, shift, pricing, now, None, "live_work_paid")
    await notify(
        conn,
        await live_work_core.business_user_id(conn, shift),
        KIND_LIVE_REQUEST,
        "Payment received — finding Workers",
        f"{shift['job_title']} is now visible to available Workers nearby.",
        {"shift_id": shift_id, "live_work": True},
    )
    return True


async def on_extension_paid(
    conn: asyncpg.Connection, invoice: asyncpg.Record, now: datetime
) -> None:
    await live_work_core.apply_paid_extension(conn, invoice, now)
