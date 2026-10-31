"""Per-process fan-out of "something changed" signals to connected sockets.

Database triggers announce changes with NOTIFY (sql/relations/realtime_notify.sql), so every
process that holds sockets hears them at commit time, whichever process made the change. Each
process keeps one LISTEN connection while it has sockets. Sockets only carry a topic name; apps
refetch through the normal (authorized) endpoints, so no data leaks through this channel.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.realtime.realtime_constants import (
    LISTEN_HEALTH_SECONDS,
    LISTEN_RETRY_SECONDS,
    NOTIFY_CHANNEL,
    NOTIFY_LIVE_PREFIX,
    NOTIFY_SHIFTS,
    TOPIC_LIVE_REQUESTS,
    TOPIC_SHIFTS,
)
from app.observability.logging import get_logger

log = get_logger(__name__)


class ListenConnection(Protocol):
    async def add_listener(self, channel: str, callback: Callable[..., Any]) -> None: ...
    def add_termination_listener(self, callback: Callable[..., Any]) -> None: ...
    async def fetchval(self, query: str, *, timeout: float) -> Any: ...
    async def close(self) -> None: ...


Connect = Callable[[], Awaitable[ListenConnection]]


@dataclass(eq=False)
class Subscription:
    """Topics changed since the socket last sent them; repeats collapse into one."""

    worker_profile_id: UUID | None
    _pending: list[str] = field(default_factory=list)
    _ready: asyncio.Event = field(default_factory=asyncio.Event)

    def push(self, topic: str) -> None:
        if topic not in self._pending:
            self._pending.append(topic)
        self._ready.set()

    async def next(self) -> str:
        await self._ready.wait()
        topic = self._pending.pop(0)
        if not self._pending:
            self._ready.clear()
        return topic


class RealtimeHub:
    def __init__(
        self,
        connect: Connect,
        retry_seconds: float = LISTEN_RETRY_SECONDS,
        health_seconds: float = LISTEN_HEALTH_SECONDS,
    ) -> None:
        self._connect = connect
        self._retry_seconds = retry_seconds
        self._health_seconds = health_seconds
        self._subscriptions: set[Subscription] = set()
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self.listening = asyncio.Event()

    def subscribe(self, worker_profile_id: UUID | None) -> Subscription:
        subscription = Subscription(worker_profile_id)
        self._subscriptions.add(subscription)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscriptions.discard(subscription)
        if not self._subscriptions:
            self._wake.set()

    def dispatch(self, payload: str) -> None:
        if payload == NOTIFY_SHIFTS:
            for subscription in self._subscriptions:
                subscription.push(TOPIC_SHIFTS)
        elif payload.startswith(NOTIFY_LIVE_PREFIX):
            worker = payload.removeprefix(NOTIFY_LIVE_PREFIX)
            for subscription in self._subscriptions:
                if str(subscription.worker_profile_id) == worker:
                    subscription.push(TOPIC_LIVE_REQUESTS)

    def _signal_everything(self) -> None:
        """After a listener gap, changes may have been missed: every socket refetches."""
        for subscription in self._subscriptions:
            subscription.push(TOPIC_SHIFTS)
            if subscription.worker_profile_id:
                subscription.push(TOPIC_LIVE_REQUESTS)

    async def _run(self) -> None:
        missed = False
        while self._subscriptions:
            try:
                conn = await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("realtime listener connect failed")
                missed = True
                await asyncio.sleep(self._retry_seconds)
                continue
            try:
                await self._listen(conn, catch_up=missed)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("realtime listener lost")
            finally:
                self.listening.clear()
                with contextlib.suppress(Exception):
                    await conn.close()
            missed = True

    async def _listen(self, conn: ListenConnection, catch_up: bool) -> None:
        lost = asyncio.Event()
        conn.add_termination_listener(lambda *_: lost.set())
        await conn.add_listener(NOTIFY_CHANNEL, lambda *args: self.dispatch(args[-1]))
        self.listening.set()
        if catch_up:
            self._signal_everything()
        while self._subscriptions and not lost.is_set():
            self._wake.clear()
            waits = [asyncio.ensure_future(lost.wait()), asyncio.ensure_future(self._wake.wait())]
            try:
                await asyncio.wait(
                    waits, timeout=self._health_seconds, return_when="FIRST_COMPLETED"
                )
            finally:
                for wait in waits:
                    wait.cancel()
            if self._subscriptions and not lost.is_set():
                await conn.fetchval("SELECT 1", timeout=self._health_seconds)


def listen_dsn(dsn: str) -> str:
    """Neon's pooled host drops notifications (transaction pooling); listen on the direct host."""
    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    if "-pooler." not in host:
        return dsn
    return urlunparse(
        parsed._replace(netloc=parsed.netloc.replace(host, host.replace("-pooler.", ".", 1)))
    )


async def _connect_listener() -> ListenConnection:
    settings = load_settings()
    return await asyncpg.connect(
        listen_dsn(settings.database_url), timeout=settings.db_connect_timeout_seconds
    )


hub = RealtimeHub(_connect_listener)
