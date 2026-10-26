"""Admin fixes on one booking after an emergency / dispute (rules §10), always with a logged
reason, plus the per-booking ledger (§11)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.notifications.notification_route_strings import KIND_BOOKING_ADJUSTED
from app.constants.support.support_route_strings import (
    ACTION_REFUND_BUSINESS,
    ACTION_REVOKE_VOUCHER,
    ACTION_UNBAN_WORKER,
    ACTION_VOID_STRIKE,
    ACTION_WAIVE_WORKER_FEE,
    ENTRY_FEE_WAIVER,
    MSG_BOOKING_NOT_FOUND,
    MSG_NO_STRIKE,
    MSG_NO_VOUCHER,
    MSG_NOTHING_TO_WAIVE,
    MSG_REFUND_AMOUNT,
    MSG_WORKER_NOT_RESTRICTED,
    WAIVABLE_ENTRY_TYPES,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.repositories.cancellations import cancellation_repository
from app.repositories.support import override_repository
from app.schemas.support.support_schemas import (
    BookingLedger,
    LedgerLine,
    OverrideRequest,
    OverrideView,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.cancellations import cancellation_service
from app.services.notifications.notification_service import notify
from app.utils.clock import utc_now


def _rupees(minor: int) -> str:
    return f"₹{minor // 100:,}.{minor % 100:02d}"


async def _load(conn: asyncpg.Connection, assignment_id: UUID) -> asyncpg.Record:
    booking = await override_repository.get_booking(conn, assignment_id)
    if booking is None:
        raise not_found("booking_not_found", MSG_BOOKING_NOT_FOUND)
    return booking


async def get_ledger(assignment_id: UUID) -> BookingLedger:
    async with get_pool().acquire() as conn:
        booking = await _load(conn, assignment_id)
        rows = await override_repository.ledger_rows(conn, assignment_id, booking["shift_id"])
    return BookingLedger(
        assignment_id=assignment_id,
        shift_id=booking["shift_id"],
        job_title=booking["job_title"],
        status=booking["status"],
        worker_name=booking["worker_name"],
        business_name=booking["business_name"],
        currency=booking["currency"],
        invoices=[
            LedgerLine(
                kind="invoice",
                amount_minor=r["total_minor"],
                description=(
                    f"{r['description']}; refund due {_rupees(r['refund_due_minor'])}"
                    + (
                        f"; promo −{_rupees(r['promo_discount_minor'])}"
                        if r["promo_discount_minor"]
                        else ""
                    )
                ),
                created_at=r["issued_at"],
            )
            for r in rows["invoices"]
        ],
        charges=[
            LedgerLine(
                kind=f"{r['party']}_{r['event']}",
                amount_minor=r["fee_minor"],
                description=(
                    f"Fee {_rupees(r['fee_minor'])}, to worker "
                    f"{_rupees(r['worker_compensation_minor'])}, kept from business "
                    f"{_rupees(r['business_retained_minor'])}"
                ),
                created_at=r["created_at"],
            )
            for r in rows["charges"]
        ],
        worker_entries=[
            LedgerLine(
                kind=r["entry_type"],
                amount_minor=r["amount_minor"],
                description=r["description"],
                created_at=r["created_at"],
            )
            for r in rows["worker_entries"]
        ],
        strikes=[
            LedgerLine(
                kind="strike_voided" if r["voided_at"] else "strike",
                amount_minor=0,
                description=f"{r['weight']} strike: {r['reason']}"
                + (f" (voided: {r['void_reason']})" if r["voided_at"] else ""),
                created_at=r["created_at"],
            )
            for r in rows["strikes"]
        ],
        vouchers=[
            LedgerLine(
                kind="voucher" if r["is_active"] else "voucher_inactive",
                amount_minor=0,
                description=f"{r['code']} · used {r['used_count']}",
                created_at=r["created_at"],
            )
            for r in rows["vouchers"]
        ],
        overrides=[OverrideView.model_validate(dict(r)) for r in rows["overrides"]],
    )


async def _waive_worker_fee(conn: asyncpg.Connection, booking: asyncpg.Record) -> int:
    if await override_repository.has_entry(conn, booking["id"], ENTRY_FEE_WAIVER):
        raise conflict("nothing_to_waive", MSG_NOTHING_TO_WAIVE)
    amount = await override_repository.sum_waivable(conn, booking["id"], WAIVABLE_ENTRY_TYPES)
    if amount <= 0:
        raise conflict("nothing_to_waive", MSG_NOTHING_TO_WAIVE)
    await cancellation_repository.insert_worker_ledger(
        conn,
        worker_profile_id=booking["worker_profile_id"],
        entry_type=ENTRY_FEE_WAIVER,
        amount_minor=amount,
        currency=booking["currency"],
        assignment_id=booking["id"],
        description=f"Fee waived by support: {booking['job_title']}",
    )
    await notify(
        conn,
        booking["worker_user_id"],
        KIND_BOOKING_ADJUSTED,
        f"{_rupees(amount)} fee refunded",
        f"Support waived the fee for {booking['job_title']}.",
        {"shift_id": booking["shift_id"], "assignment_id": booking["id"]},
    )
    return amount


async def _void_strike(
    conn: asyncpg.Connection, booking: asyncpg.Record, admin: AuthenticatedUser, reason: str
) -> None:
    now = utc_now()
    worker_profile_id = await override_repository.void_strike(
        conn, booking["id"], now=now, admin_id=admin.user_id, reason=reason
    )
    if worker_profile_id is None:
        raise conflict("no_strike", MSG_NO_STRIKE)
    policy = await cancellation_service.load_policy(conn)
    weight = await cancellation_repository.active_strike_weight(conn, worker_profile_id, now)
    await override_repository.lift_restrictions(
        conn,
        worker_profile_id,
        unban=weight < policy.strikes_to_ban,
        unlimit=weight < policy.strikes_to_limit,
    )
    await notify(
        conn,
        booking["worker_user_id"],
        KIND_BOOKING_ADJUSTED,
        "A strike was removed",
        f"Support removed the strike for {booking['job_title']}.",
        {"shift_id": booking["shift_id"], "assignment_id": booking["id"]},
    )


async def _refund_business(
    conn: asyncpg.Connection, booking: asyncpg.Record, amount: int | None
) -> int:
    invoice = await override_repository.lock_refundable_invoice(conn, booking["shift_id"])
    room = invoice["total_minor"] - invoice["refund_due_minor"] if invoice else 0
    if not amount or amount > room:
        raise bad_request("refund_amount_invalid", MSG_REFUND_AMOUNT, {"max_minor": room})
    await override_repository.add_refund_due(conn, invoice["id"], amount)
    await notify(
        conn,
        booking["business_user_id"],
        KIND_BOOKING_ADJUSTED,
        f"{_rupees(amount)} refund approved",
        f"Support approved a refund for {booking['job_title']}.",
        {"shift_id": booking["shift_id"], "invoice_id": invoice["id"]},
    )
    return amount


async def apply_override(
    admin: AuthenticatedUser, assignment_id: UUID, body: OverrideRequest
) -> OverrideView:
    reason = body.reason.strip()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            booking = await _load(conn, assignment_id)
            amount = 0
            if body.action == ACTION_WAIVE_WORKER_FEE:
                amount = await _waive_worker_fee(conn, booking)
            elif body.action == ACTION_VOID_STRIKE:
                await _void_strike(conn, booking, admin, reason)
            elif body.action == ACTION_UNBAN_WORKER:
                if not await override_repository.lift_restrictions(
                    conn, booking["worker_profile_id"], unban=True, unlimit=True
                ):
                    raise conflict("worker_not_restricted", MSG_WORKER_NOT_RESTRICTED)
            elif body.action == ACTION_REVOKE_VOUCHER:
                if not await override_repository.deactivate_booking_voucher(conn, assignment_id):
                    raise conflict("no_voucher", MSG_NO_VOUCHER)
            elif body.action == ACTION_REFUND_BUSINESS:
                amount = await _refund_business(conn, booking, body.amount_minor)
            row = await override_repository.insert_override(
                conn,
                assignment_id=assignment_id,
                support_ticket_id=body.support_ticket_id,
                action=body.action,
                amount_minor=amount,
                reason=reason,
                admin_user_id=admin.user_id,
            )
    return OverrideView.model_validate(dict(row))
