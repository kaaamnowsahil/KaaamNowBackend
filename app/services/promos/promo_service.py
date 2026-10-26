"""Promo codes: business enters one when posting, worker enters one from the wallet for the
next payout's commission. Free-fees vouchers are single-use codes owned by one business."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.constants.application.application_constants import ROLE_BUSINESS, ROLE_WORKER
from app.constants.promos.promo_route_strings import (
    ENTRY_PROMO_CREDIT,
    MSG_PROMO_INVALID,
    MSG_PROMO_PENDING,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request, conflict
from app.repositories.cancellations import cancellation_repository
from app.repositories.profiles import profile_repository
from app.repositories.promos import promo_repository
from app.schemas.promos.promo_schemas import PromoList, PromoView, WorkerPromoStatus
from app.security.authenticated_user import AuthenticatedUser
from app.services.promos.promo_rules import Promo, promo_problem, worker_commission_discount
from app.utils.clock import utc_now


def promo_view(row: asyncpg.Record) -> PromoView:
    return PromoView(
        id=row["id"],
        code=row["code"],
        discount_type=row["discount_type"],
        discount_value=float(row["discount_value"]),
        applies_to=row["applies_to"],
        max_discount_minor=row["max_discount_minor"],
        valid_until=row["valid_until"],
        is_voucher=row["owner_user_id"] is not None,
    )


def _invalid(reason: str) -> ApiError:
    return bad_request("promo_invalid", MSG_PROMO_INVALID[reason], {"reason": reason})


async def usable(
    conn: asyncpg.Connection,
    code: str,
    *,
    role: str,
    user_id: UUID,
    now: datetime,
    lock: bool = False,
) -> asyncpg.Record:
    row = await (promo_repository.lock_by_code if lock else promo_repository.get_by_code)(
        conn, code
    )
    uses = await promo_repository.count_user_uses(conn, row["id"], user_id) if row else 0
    reason = promo_problem(row, role=role, user_id=user_id, now=now, user_uses=uses)
    if reason:
        raise _invalid(reason)
    return row


# --- business ---------------------------------------------------------------------------


async def attach_business_code(
    conn: asyncpg.Connection, shift_id: UUID, code: str, user_id: UUID
) -> None:
    """Code typed on the post-shift form. It is reserved when the shift is published."""
    row = await usable(conn, code, role=ROLE_BUSINESS, user_id=user_id, now=utc_now())
    await promo_repository.attach_to_shift(conn, shift_id, row["id"])


async def reserve_for_shift(
    conn: asyncpg.Connection, shift: asyncpg.Record, user_id: UUID, now: datetime
) -> None:
    if shift["promo_code_id"] is None:
        return
    if await promo_repository.lock_shift_redemption(conn, shift["id"]):
        return
    promo = await promo_repository.get_by_id(conn, shift["promo_code_id"])
    row = await usable(conn, promo["code"], role=ROLE_BUSINESS, user_id=user_id, now=now, lock=True)
    await promo_repository.reserve(conn, row["id"], user_id, shift["id"])


async def shift_promo(conn: asyncpg.Connection, shift: asyncpg.Record) -> Promo | None:
    """The promo reserved for this shift (None when there's none or it was released)."""
    if shift["promo_code_id"] is None:
        return None
    redemption = await promo_repository.lock_shift_redemption(conn, shift["id"])
    if redemption is None:
        return None
    return Promo.from_row(await promo_repository.get_by_id(conn, redemption["promo_code_id"]))


async def preview_promo(conn: asyncpg.Connection, shift: asyncpg.Record) -> Promo | None:
    """Promo for estimates: the attached code even before it is reserved."""
    if shift["promo_code_id"] is None:
        return None
    row = await promo_repository.get_by_id(conn, shift["promo_code_id"])
    return Promo.from_row(row) if row else None


async def mark_shift_applied(
    conn: asyncpg.Connection, shift_id: UUID, discount_minor: int, now: datetime
) -> None:
    redemption = await promo_repository.lock_shift_redemption(conn, shift_id)
    if redemption is not None and redemption["status"] == "reserved":
        await promo_repository.apply(
            conn, redemption["id"], discount_minor=discount_minor, assignment_id=None, now=now
        )


async def release_for_shift(conn: asyncpg.Connection, shift_id: UUID, now: datetime) -> None:
    """Shift cancelled / expired before it ran: the code can be used again."""
    redemption = await promo_repository.lock_shift_redemption(conn, shift_id)
    if redemption is not None and redemption["status"] == "reserved":
        await promo_repository.release(conn, redemption, now)


async def validate(user: AuthenticatedUser, code: str, role: str) -> PromoView:
    async with get_pool().acquire() as conn:
        return promo_view(await usable(conn, code, role=role, user_id=user.user_id, now=utc_now()))


async def list_business_vouchers(user: AuthenticatedUser) -> PromoList:
    async with get_pool().acquire() as conn:
        rows = await promo_repository.list_owned_vouchers(conn, user.user_id, utc_now())
    return PromoList(items=[promo_view(r) for r in rows])


# --- worker -----------------------------------------------------------------------------


async def worker_status(user: AuthenticatedUser) -> WorkerPromoStatus:
    async with get_pool().acquire() as conn:
        pending = await promo_repository.lock_worker_pending(conn, user.user_id)
        if pending is None:
            return WorkerPromoStatus(pending=None)
        row = await promo_repository.get_by_id(conn, pending["promo_code_id"])
    return WorkerPromoStatus(pending=promo_view(row))


async def redeem_worker(user: AuthenticatedUser, code: str) -> WorkerPromoStatus:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            if await promo_repository.lock_worker_pending(conn, user.user_id):
                raise conflict("promo_pending", MSG_PROMO_PENDING)
            row = await usable(
                conn, code, role=ROLE_WORKER, user_id=user.user_id, now=now, lock=True
            )
            await promo_repository.reserve(conn, row["id"], user.user_id, None)
    return WorkerPromoStatus(pending=promo_view(row))


async def apply_worker_promos(
    conn: asyncpg.Connection, commissions: list[asyncpg.Record], currency: str, now: datetime
) -> dict[UUID, int]:
    """Each worker's pending code takes its discount off this payout's commission.
    Returns ``worker_profile_id → credit``."""
    credits: dict[UUID, int] = {}
    for row in commissions:
        worker = await profile_repository.get_worker_profile(conn, row["worker_profile_id"])
        pending = await promo_repository.lock_worker_pending(conn, worker["user_id"])
        if pending is None:
            continue
        promo = Promo.from_row(await promo_repository.get_by_id(conn, pending["promo_code_id"]))
        credit = worker_commission_discount(promo, -row["amount_minor"])
        if credit <= 0:
            continue
        await cancellation_repository.insert_worker_ledger(
            conn,
            worker_profile_id=row["worker_profile_id"],
            entry_type=ENTRY_PROMO_CREDIT,
            amount_minor=credit,
            currency=currency,
            assignment_id=row["assignment_id"],
            description=f"Promo {promo.code}: commission discount",
        )
        await promo_repository.apply(
            conn,
            pending["id"],
            discount_minor=credit,
            assignment_id=row["assignment_id"],
            now=now,
        )
        credits[row["worker_profile_id"]] = credit
    return credits
