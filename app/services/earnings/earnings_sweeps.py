"""Poll payout provider for in-flight withdrawals; reverse the debit on failure."""

from __future__ import annotations

import asyncpg

from app.constants.earnings.earnings_route_strings import (
    ENTRY_WITHDRAWAL_REVERSAL,
    WD_FAILED,
    WD_PAID,
    WITHDRAWAL_SWEEP_BATCH,
)
from app.constants.notifications.notification_route_strings import (
    KIND_WITHDRAWAL_FAILED,
    KIND_WITHDRAWAL_PAID,
)
from app.repositories.earnings import earnings_repository
from app.services.earnings.sources.payout_provider_factory import get_payout_provider
from app.services.notifications.notification_service import notify
from app.utils.clock import utc_now


async def advance_processing_withdrawals(pool: asyncpg.Pool) -> int:
    finished = 0
    async with pool.acquire() as conn:
        for withdrawal_id in await earnings_repository.list_in_flight_withdrawal_ids(
            conn, WITHDRAWAL_SWEEP_BATCH
        ):
            async with conn.transaction():
                row = await earnings_repository.lock_withdrawal(conn, withdrawal_id)
                if row is None or row["status"] not in ("initiated", "processing"):
                    continue
                if not row["provider_payout_id"]:
                    continue
                status = await get_payout_provider(row["provider"]).fetch_status(
                    row["provider_payout_id"]
                )
                now = utc_now()
                amount = row["amount_minor"]
                label = f"₹{amount // 100:,}.{amount % 100:02d}"
                if status.status == WD_PAID:
                    await earnings_repository.finish_withdrawal(
                        conn, withdrawal_id, status=WD_PAID, failure_reason=None, now=now
                    )
                    await notify(
                        conn,
                        row["user_id"],
                        KIND_WITHDRAWAL_PAID,
                        "Withdrawal successful",
                        f"{label} sent · {row['reference']}",
                        {"withdrawal_id": withdrawal_id},
                    )
                    finished += 1
                elif status.status == WD_FAILED:
                    await earnings_repository.lock_worker_ledger(conn, row["worker_profile_id"])
                    await earnings_repository.finish_withdrawal(
                        conn,
                        withdrawal_id,
                        status=WD_FAILED,
                        failure_reason=(status.failure_reason or "")[:200],
                        now=now,
                    )
                    await earnings_repository.insert_ledger_entry(
                        conn,
                        worker_profile_id=row["worker_profile_id"],
                        entry_type=ENTRY_WITHDRAWAL_REVERSAL,
                        amount_minor=amount,
                        currency=row["currency"],
                        withdrawal_id=withdrawal_id,
                        description=f"Reversal of {row['reference']}",
                    )
                    await notify(
                        conn,
                        row["user_id"],
                        KIND_WITHDRAWAL_FAILED,
                        "Withdrawal failed",
                        f"{label} is back in your balance. {status.failure_reason or ''}".strip(),
                        {"withdrawal_id": withdrawal_id},
                    )
                    finished += 1
    return finished
