"""Admin dashboard overview counters computed from live tables."""

from __future__ import annotations

from collections.abc import Iterable

import asyncpg

from app.constants.admin.admin_route_strings import (
    INVOICE_STATUS_PAID,
    PAYMENT_STATUS_SUCCEEDED,
    SUPPORT_STATUS_OPEN,
    WITHDRAWAL_PENDING_STATUSES,
    WITHDRAWAL_STATUS_PAID,
)
from app.db.pool import get_pool
from app.repositories.admin import admin_repository
from app.schemas.admin.admin_schemas import AdminCount, AdminMetricsOverview


def _counts(rows: Iterable[asyncpg.Record]) -> list[AdminCount]:
    return [AdminCount(key=r["key"], count=r["count"]) for r in rows]


async def overview() -> AdminMetricsOverview:
    async with get_pool().acquire() as conn:
        scalars = await admin_repository.metrics_scalars(
            conn,
            open_ticket_status=SUPPORT_STATUS_OPEN,
            pending_withdrawal_statuses=WITHDRAWAL_PENDING_STATUSES,
            paid_withdrawal_status=WITHDRAWAL_STATUS_PAID,
            paid_invoice_status=INVOICE_STATUS_PAID,
            succeeded_payment_status=PAYMENT_STATUS_SUCCEEDED,
        )
        workers = await admin_repository.workers_by_verification(conn)
        businesses = await admin_repository.businesses_by_verification(conn)
        shifts = await admin_repository.shifts_by_status(conn)
    return AdminMetricsOverview(
        **{k: int(v) for k, v in dict(scalars).items()},
        workers_by_verification=_counts(workers),
        businesses_by_verification=_counts(businesses),
        shifts_by_status=_counts(shifts),
    )
