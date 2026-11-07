"""Admin settlement of manual withdrawals: pay outside the app, then record the proof.

Mark paid needs a payment screenshot; reject puts the amount back in the worker's balance with a
``withdrawal_reversal`` entry, the same way a failed provider payout does.
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.constants.earnings.earnings_route_strings import (
    ENTRY_WITHDRAWAL_REVERSAL,
    MSG_WITHDRAWAL_NOT_FOUND,
    MSG_WITHDRAWAL_NOT_MANUAL,
    MSG_WITHDRAWAL_NOT_OPEN,
    PAYOUT_PROOF_STORAGE_FOLDER,
    PAYOUT_PROVIDER_MANUAL,
    WD_FAILED,
    WD_OPEN_STATUSES,
    WD_PAID,
    WITHDRAWAL_RESOURCE,
)
from app.constants.notifications.notification_route_strings import (
    KIND_WITHDRAWAL_FAILED,
    KIND_WITHDRAWAL_PAID,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.repositories.admin import admin_repository
from app.repositories.earnings import earnings_repository
from app.schemas.earnings.earnings_schemas import ManualPayoutView
from app.security.authenticated_user import AuthenticatedUser
from app.services.notifications.notification_service import notify
from app.services.users.sources.photo_storage import (
    delete_images,
    get_photo_storage,
    validate_image,
)
from app.utils.clock import utc_now


def _label(amount_minor: int) -> str:
    return f"₹{amount_minor // 100:,}.{amount_minor % 100:02d}".replace(".00", "")


def _audit(row: asyncpg.Record) -> str:
    return json.dumps(
        {
            "status": row["status"],
            "failure_reason": row["failure_reason"],
            "payout_utr": row["payout_utr"],
            "proof_url": row["proof_url"],
        }
    )


def _view(row: asyncpg.Record) -> ManualPayoutView:
    return ManualPayoutView(
        id=row["id"],
        status=row["status"],
        failure_reason=row["failure_reason"],
        payout_utr=row["payout_utr"],
        proof_url=row["proof_url"],
        completed_at=row["completed_at"],
    )


def _require_open_manual(row: asyncpg.Record | None) -> asyncpg.Record:
    if row is None:
        raise not_found("withdrawal_not_found", MSG_WITHDRAWAL_NOT_FOUND)
    if row["provider"] != PAYOUT_PROVIDER_MANUAL:
        raise conflict("withdrawal_not_manual", MSG_WITHDRAWAL_NOT_MANUAL)
    if row["status"] not in WD_OPEN_STATUSES:
        raise conflict("withdrawal_not_open", MSG_WITHDRAWAL_NOT_OPEN)
    return row


async def mark_paid(
    admin: AuthenticatedUser,
    withdrawal_id: UUID,
    *,
    content_type: str,
    proof: bytes,
    utr: str | None,
) -> ManualPayoutView:
    extension = validate_image(content_type, proof)
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            _require_open_manual(await earnings_repository.lock_withdrawal(conn, withdrawal_id))
    proof_url = await get_photo_storage().save(PAYOUT_PROOF_STORAGE_FOLDER, proof, extension)
    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                row = _require_open_manual(
                    await earnings_repository.lock_withdrawal(conn, withdrawal_id)
                )
                await earnings_repository.settle_withdrawal(
                    conn,
                    withdrawal_id,
                    status=WD_PAID,
                    failure_reason=None,
                    proof_url=proof_url,
                    payout_utr=utr,
                    settled_by_user_id=admin.user_id,
                    now=utc_now(),
                )
                updated = await earnings_repository.lock_withdrawal(conn, withdrawal_id)
                await admin_repository.insert_audit(
                    conn,
                    resource=WITHDRAWAL_RESOURCE,
                    record_id=str(withdrawal_id),
                    action="update",
                    actor_user_id=admin.user_id,
                    old_values=_audit(row),
                    new_values=_audit(updated),
                )
                body = f"{_label(row['amount_minor'])} sent · {row['reference']}"
                await notify(
                    conn,
                    row["user_id"],
                    KIND_WITHDRAWAL_PAID,
                    "Withdrawal successful",
                    f"{body} · UTR {utr}" if utr else body,
                    {"withdrawal_id": withdrawal_id},
                )
    except BaseException:
        await delete_images([proof_url])
        raise
    return _view(updated)


async def reject(admin: AuthenticatedUser, withdrawal_id: UUID, reason: str) -> ManualPayoutView:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            row = _require_open_manual(
                await earnings_repository.lock_withdrawal(conn, withdrawal_id)
            )
            await earnings_repository.lock_worker_ledger(conn, row["worker_profile_id"])
            await earnings_repository.settle_withdrawal(
                conn,
                withdrawal_id,
                status=WD_FAILED,
                failure_reason=reason,
                proof_url=None,
                payout_utr=None,
                settled_by_user_id=admin.user_id,
                now=utc_now(),
            )
            await earnings_repository.insert_ledger_entry(
                conn,
                worker_profile_id=row["worker_profile_id"],
                entry_type=ENTRY_WITHDRAWAL_REVERSAL,
                amount_minor=row["amount_minor"],
                currency=row["currency"],
                withdrawal_id=withdrawal_id,
                description=f"Reversal of {row['reference']}",
            )
            updated = await earnings_repository.lock_withdrawal(conn, withdrawal_id)
            await admin_repository.insert_audit(
                conn,
                resource=WITHDRAWAL_RESOURCE,
                record_id=str(withdrawal_id),
                action="update",
                actor_user_id=admin.user_id,
                old_values=_audit(row),
                new_values=_audit(updated),
            )
            await notify(
                conn,
                row["user_id"],
                KIND_WITHDRAWAL_FAILED,
                "Withdrawal failed",
                f"{_label(row['amount_minor'])} is back in your balance. {reason}",
                {"withdrawal_id": withdrawal_id},
            )
    return _view(updated)
