"""Realtime signals against the real schema: a Live post reaches the right sockets."""

from __future__ import annotations

import asyncio

import pytest

from app.constants.realtime.realtime_constants import TOPIC_LIVE_REQUESTS, TOPIC_SHIFTS
from app.services.realtime import realtime_service
from app.services.realtime.realtime_hub import RealtimeHub, Subscription, _connect_listener
from tests.integration.test_live_work import _location, _place_worker, _searching

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _topics(subscription: Subscription, wait: float = 0.5) -> set[str]:
    """Collects signals until none arrive for ``wait`` seconds (NOTIFY lands after commit)."""
    topics = set()
    while True:
        try:
            topics.add(await asyncio.wait_for(subscription.next(), wait))
        except TimeoutError:
            return topics


def _token(actor) -> str:  # type: ignore[no-untyped-def]
    return actor.headers["Authorization"].removeprefix("Bearer ")


async def test_identify_by_token(app_client, make_business, make_worker) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    worker = await make_worker("Realtime Id")
    assert await realtime_service.identify(_token(worker)) == worker.profile_id
    assert await realtime_service.identify(_token(business)) is None


async def test_live_post_signals_feed_and_the_offered_worker(
    app_client, make_business, make_worker
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    offered = await make_worker("Realtime Near")
    elsewhere = await make_worker("Realtime Far")
    lat, lng = _location()
    await _place_worker(app_client, offered, lat, lng)

    hub = RealtimeHub(_connect_listener)
    near = hub.subscribe(offered.profile_id)
    far = hub.subscribe(elsewhere.profile_id)
    owner = hub.subscribe(None)
    try:
        await asyncio.wait_for(hub.listening.wait(), 5)
        await _searching(app_client, business, lat, lng)

        assert await _topics(near) == {TOPIC_SHIFTS, TOPIC_LIVE_REQUESTS}
        assert await _topics(far) == {TOPIC_SHIFTS}
        assert await _topics(owner) == {TOPIC_SHIFTS}
        assert await _topics(near, wait=0.2) == set()
    finally:
        assert hub._task is not None
        hub._task.cancel()
