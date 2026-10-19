"""Single in-process loop that runs every time-based state transition.

Only one API replica runs a sweep at a time (``pg_try_advisory_lock``). Each job is
idempotent and owns its own transactions, so a crash mid-sweep is safe.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import asyncpg

from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)

_SWEEP_ADVISORY_LOCK_KEY = 7_420_002

SweepJob = Callable[[asyncpg.Pool], Awaitable[int]]

_task: asyncio.Task[None] | None = None


def _jobs() -> list[tuple[str, SweepJob]]:
    from app.services.billing.billing_sweeps import expire_stale_payments
    from app.services.earnings.earnings_sweeps import advance_processing_withdrawals
    from app.services.notifications.notification_sweeps import deliver_pending_pushes
    from app.services.shifts.shift_sweeps import (
        expand_live_search_radius,
        expire_live_offers,
        expire_selection_confirmations,
        finish_live_searches,
        mark_scheduled_shifts_started,
    )

    return [
        ("expire_live_offers", expire_live_offers),
        ("expand_live_search_radius", expand_live_search_radius),
        ("finish_live_searches", finish_live_searches),
        ("expire_selection_confirmations", expire_selection_confirmations),
        ("mark_scheduled_shifts_started", mark_scheduled_shifts_started),
        ("expire_stale_payments", expire_stale_payments),
        ("advance_processing_withdrawals", advance_processing_withdrawals),
        ("deliver_pending_pushes", deliver_pending_pushes),
    ]


async def run_sweep_once(pool: asyncpg.Pool) -> dict[str, int]:
    """Run every job once (used by the loop and by integration tests)."""
    results: dict[str, int] = {}
    for name, job in _jobs():
        try:
            results[name] = await job(pool)
        except Exception:
            log.exception("sweep job failed", extra=log_extra(job=name))
            results[name] = -1
    return results


async def _loop(pool: asyncpg.Pool, interval_seconds: int) -> None:
    while True:
        try:
            async with pool.acquire() as conn:
                locked = await conn.fetchval(
                    "SELECT pg_try_advisory_lock($1)", _SWEEP_ADVISORY_LOCK_KEY
                )
                if locked:
                    try:
                        results = await run_sweep_once(pool)
                        changed = {k: v for k, v in results.items() if v}
                        if changed:
                            log.info("sweep", extra=log_extra(**changed))
                    finally:
                        await conn.execute(
                            "SELECT pg_advisory_unlock($1)", _SWEEP_ADVISORY_LOCK_KEY
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sweep loop iteration failed")
        await asyncio.sleep(interval_seconds)


async def start_background_sweep_loop(pool: asyncpg.Pool, interval_seconds: int) -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(pool, interval_seconds), name="kaamnow-sweep")


async def stop_background_sweep_loop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
