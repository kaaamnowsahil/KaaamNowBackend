"""Realtime hub signal rules and the socket session (auth, origin, forwarding, cleanup)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import WebSocketDisconnect

from app.constants.realtime.realtime_constants import (
    CLOSE_POLICY_VIOLATION,
    CLOSE_UNAUTHORIZED,
    NOTIFY_CHANNEL,
    NOTIFY_LIVE_PREFIX,
    NOTIFY_SHIFTS,
    TOPIC_LIVE_REQUESTS,
    TOPIC_SHIFTS,
)
from app.exceptions.api_errors import AuthenticationError
from app.services.realtime import realtime_service
from app.services.realtime.realtime_hub import RealtimeHub, Subscription, listen_dsn

ALLOWED = "https://www.kaaamnow.in"


async def _topics(subscription: Subscription) -> list[str]:
    topics = []
    while True:
        try:
            topics.append(await asyncio.wait_for(subscription.next(), 0.01))
        except TimeoutError:
            return topics


class _FakeListen:
    """Stands in for the asyncpg LISTEN connection."""

    def __init__(self) -> None:
        self.notify: Callable[..., Any] | None = None
        self.terminate: Callable[..., Any] | None = None
        self.closed = False

    async def add_listener(self, channel: str, callback: Callable[..., Any]) -> None:
        assert channel == NOTIFY_CHANNEL
        self.notify = callback

    def add_termination_listener(self, callback: Callable[..., Any]) -> None:
        self.terminate = callback

    async def fetchval(self, query: str, *, timeout: float) -> int:
        return 1

    async def close(self) -> None:
        self.closed = True

    def send(self, payload: str) -> None:
        assert self.notify is not None
        self.notify(self, 1, NOTIFY_CHANNEL, payload)


class _Connector:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.connections: list[_FakeListen] = []

    async def __call__(self) -> _FakeListen:
        if self.failures:
            self.failures -= 1
            raise OSError("database unavailable")
        self.connections.append(_FakeListen())
        return self.connections[-1]


def _hub(connector: _Connector) -> RealtimeHub:
    return RealtimeHub(connector, retry_seconds=0.01, health_seconds=0.05)


def _stop(hub: RealtimeHub) -> None:
    if hub._task is not None:
        hub._task.cancel()


async def test_notifications_reach_the_right_sockets_and_repeats_collapse() -> None:
    connector = _Connector()
    hub = _hub(connector)
    one, two = uuid4(), uuid4()
    first, second, business = hub.subscribe(one), hub.subscribe(two), hub.subscribe(None)
    try:
        await asyncio.wait_for(hub.listening.wait(), 1)
        listen = connector.connections[0]

        listen.send(NOTIFY_SHIFTS)
        listen.send(f"{NOTIFY_LIVE_PREFIX}{one}")
        listen.send(f"{NOTIFY_LIVE_PREFIX}{one}")
        listen.send("unknown")

        assert await _topics(first) == [TOPIC_SHIFTS, TOPIC_LIVE_REQUESTS]
        assert await _topics(second) == [TOPIC_SHIFTS]
        assert await _topics(business) == [TOPIC_SHIFTS]
    finally:
        _stop(hub)


async def test_a_lost_listener_reconnects_and_everyone_refetches() -> None:
    connector = _Connector()
    hub = _hub(connector)
    worker, business = hub.subscribe(uuid4()), hub.subscribe(None)
    try:
        await asyncio.wait_for(hub.listening.wait(), 1)
        assert await _topics(worker) == []
        first = connector.connections[0]
        assert first.terminate is not None
        first.terminate(first)

        for _ in range(100):
            if len(connector.connections) == 2 and hub.listening.is_set():
                break
            await asyncio.sleep(0.01)
        assert first.closed
        assert await _topics(worker) == [TOPIC_SHIFTS, TOPIC_LIVE_REQUESTS]
        assert await _topics(business) == [TOPIC_SHIFTS]
    finally:
        _stop(hub)


async def test_connect_failures_retry_then_catch_up() -> None:
    connector = _Connector(failures=2)
    hub = _hub(connector)
    worker = hub.subscribe(uuid4())
    try:
        await asyncio.wait_for(hub.listening.wait(), 1)
        assert len(connector.connections) == 1
        assert await _topics(worker) == [TOPIC_SHIFTS, TOPIC_LIVE_REQUESTS]
    finally:
        _stop(hub)


async def test_the_listener_closes_when_the_last_socket_leaves() -> None:
    connector = _Connector()
    hub = _hub(connector)
    subscription = hub.subscribe(uuid4())
    await asyncio.wait_for(hub.listening.wait(), 1)
    hub.unsubscribe(subscription)
    assert hub._task is not None
    await asyncio.wait_for(hub._task, 1)
    assert connector.connections[0].closed and not hub.listening.is_set()


def test_listen_dsn_uses_the_direct_neon_host() -> None:
    pooled = "postgresql://u:p@ep-cool-1-pooler.ap-south-1.aws.neon.tech/db?sslmode=require"
    assert listen_dsn(pooled) == (
        "postgresql://u:p@ep-cool-1.ap-south-1.aws.neon.tech/db?sslmode=require"
    )
    assert listen_dsn("postgresql://me@localhost:5432/db") == "postgresql://me@localhost:5432/db"


def test_origin_rules() -> None:
    allowed = f"{ALLOWED},http://localhost:5173"
    assert realtime_service.origin_allowed(None, allowed)
    assert realtime_service.origin_allowed(ALLOWED, allowed)
    assert not realtime_service.origin_allowed("https://evil.example", allowed)
    assert realtime_service.origin_allowed("https://any.example", "*")


class _FakeSocket:
    def __init__(self, *messages: object, origin: str | None = ALLOWED) -> None:
        self.headers = {"origin": origin} if origin else {}
        self.incoming: asyncio.Queue[dict] = asyncio.Queue()
        for message in messages:
            self.incoming.put_nowait({"type": "websocket.receive", "text": json.dumps(message)})
        self.sent: list[dict] = []
        self.accepted = False
        self.closed: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict:
        return await self.incoming.get()

    async def receive_json(self) -> object:
        message = await self.incoming.get()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect()
        return json.loads(message["text"])

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed = code

    def leave(self) -> None:
        self.incoming.put_nowait({"type": "websocket.disconnect"})


class _FakeHub:
    def __init__(self) -> None:
        self.subscriptions: list[Subscription] = []
        self.removed: list[Subscription] = []

    def subscribe(self, worker_profile_id: UUID | None) -> Subscription:
        subscription = Subscription(worker_profile_id)
        self.subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self.removed.append(subscription)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        realtime_service, "load_settings", lambda: SimpleNamespace(cors_origin=ALLOWED)
    )


async def _until(condition) -> None:  # type: ignore[no-untyped-def]
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met")


async def test_unknown_origin_is_refused_before_accepting() -> None:
    socket, hub = _FakeSocket(origin="https://evil.example"), _FakeHub()
    await realtime_service.serve(socket, hub)  # type: ignore[arg-type]
    assert not socket.accepted and socket.closed == CLOSE_POLICY_VIOLATION
    assert hub.subscriptions == []


@pytest.mark.parametrize(
    "first_message",
    [{"type": "auth", "token": "bad"}, {"type": "hello"}, {"type": "auth"}, ["auth"]],
)
async def test_bad_auth_closes_without_subscribing(
    monkeypatch: pytest.MonkeyPatch, first_message: object
) -> None:
    async def reject(_token: str) -> UUID | None:
        raise AuthenticationError("invalid")

    monkeypatch.setattr(realtime_service, "identify", reject)
    socket, hub = _FakeSocket(first_message), _FakeHub()
    await realtime_service.serve(socket, hub)  # type: ignore[arg-type]
    assert socket.closed == CLOSE_UNAUTHORIZED
    assert hub.subscriptions == [] and socket.sent == []


async def test_forwards_changes_and_unsubscribes_when_the_client_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_id = uuid4()
    seen: list[str] = []

    async def accept(token: str) -> UUID | None:
        seen.append(token)
        return worker_id

    monkeypatch.setattr(realtime_service, "identify", accept)
    socket, hub = _FakeSocket({"type": "auth", "token": "good"}), _FakeHub()
    session = asyncio.create_task(realtime_service.serve(socket, hub))  # type: ignore[arg-type]

    await _until(lambda: socket.sent == [{"type": "ready"}])
    assert seen == ["good"] and hub.subscriptions[0].worker_profile_id == worker_id

    hub.subscriptions[0].push(TOPIC_SHIFTS)
    await _until(lambda: {"type": "changed", "topic": TOPIC_SHIFTS} in socket.sent)

    socket.leave()
    await asyncio.wait_for(session, 1)
    assert hub.removed == hub.subscriptions
