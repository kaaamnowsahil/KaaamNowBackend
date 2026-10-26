"""Release worker earnings for a settled final invoice (gross pay, then commission debit)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.notifications.notification_route_strings import KIND_EARNING_CREDITED
from app.repositories.earnings import earnings_repository
from app.repositories.profiles import profile_repository
from app.services.notifications.notification_service import notify
from app.services.promos import promo_service
from app.utils.clock import utc_now


async def release_invoice_earnings(conn: asyncpg.Connection, invoice_id: UUID) -> None:
    """Idempotent: re-running for the same invoice credits nothing new."""
    credited = await earnings_repository.credit_invoice_earnings(conn, invoice_id)
    if not credited:
        return
    debited = await earnings_repository.debit_invoice_commissions(conn, invoice_id)
    commissions = {r["worker_profile_id"]: r["amount_minor"] for r in debited}
    if debited:
        promo_credits = await promo_service.apply_worker_promos(
            conn, debited, debited[0]["currency"], utc_now()
        )
        for worker_profile_id, credit in promo_credits.items():
            commissions[worker_profile_id] += credit
    await profile_repository.increment_completed_shifts(
        conn, [r["worker_profile_id"] for r in credited]
    )
    for row in credited:
        worker = await profile_repository.get_worker_profile(conn, row["worker_profile_id"])
        net = row["amount_minor"] + commissions.get(row["worker_profile_id"], 0)
        await notify(
            conn,
            worker["user_id"],
            KIND_EARNING_CREDITED,
            "Payment received",
            f"₹{net // 100:,}.{net % 100:02d} added to your earnings",
            {"invoice_id": invoice_id, "amount_minor": net},
        )
