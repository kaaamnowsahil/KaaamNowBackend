"""Single in-process loop that runs every time-based state transition.

Only one API replica runs a sweep at a time (``pg_try_advisory_lock``). Each job is
idempotent and owns its own transactions, so a crash mid-sweep is safe.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections.abc import Awaitable, Callable

import asyncpg
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db.pool import get_pool
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
        close_scheduled_recruiting,
        expire_live_offers,
        expire_selection_confirmations,
        finish_live_searches,
        prompt_extensions,
        refresh_live_searches,
        release_unfilled_seats,
    )
    from app.services.users.deletion_service import (
        expire_holds,
        process_deletion_requests,
    )

    return [
        ("expire_live_offers", expire_live_offers),
        ("refresh_live_searches", refresh_live_searches),
        ("finish_live_searches", finish_live_searches),
        ("expire_selection_confirmations", expire_selection_confirmations),
        ("release_unfilled_seats", release_unfilled_seats),
        ("prompt_extensions", prompt_extensions),
        ("close_scheduled_recruiting", close_scheduled_recruiting),
        ("expire_stale_payments", expire_stale_payments),
        ("advance_processing_withdrawals", advance_processing_withdrawals),
        ("deliver_pending_pushes", deliver_pending_pushes),
        ("expire_deletion_holds", expire_holds),
        ("process_deletion_requests", process_deletion_requests),
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


async def run_locked_sweep(pool: asyncpg.Pool) -> None:
    """Run one sweep unless another replica holds the sweep lock."""
    async with pool.acquire() as conn:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock($1)", _SWEEP_ADVISORY_LOCK_KEY)
        if not locked:
            return
        try:
            results = await run_sweep_once(pool)
            changed = {k: v for k, v in results.items() if v}
            if changed:
                log.info("sweep", extra=log_extra(**changed))
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _SWEEP_ADVISORY_LOCK_KEY)


async def _loop(pool: asyncpg.Pool, interval_seconds: int) -> None:
    while True:
        try:
            await run_locked_sweep(pool)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sweep loop iteration failed")
        await asyncio.sleep(interval_seconds)


class RequestSweepMiddleware:
    """Runs the sweep before an HTTP request when the last one is older than the interval.

    The sweep is awaited inline: work scheduled after the response may be frozen on
    serverless hosts while it still holds the advisory lock.
    """

    def __init__(self, app: ASGIApp, interval_seconds: int) -> None:
        self.app = app
        self.interval_seconds = interval_seconds
        self._last_sweep_at = -math.inf

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self._maybe_sweep()
        await self.app(scope, receive, send)

    async def _maybe_sweep(self) -> None:
        now = time.monotonic()
        if now - self._last_sweep_at < self.interval_seconds:
            return
        self._last_sweep_at = now
        try:
            await run_locked_sweep(get_pool())
        except Exception:
            log.exception("request sweep failed")


async def start_background_sweep_loop(pool: asyncpg.Pool, interval_seconds: int) -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(pool, interval_seconds), name="kaaamnow-sweep")


async def stop_background_sweep_loop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
