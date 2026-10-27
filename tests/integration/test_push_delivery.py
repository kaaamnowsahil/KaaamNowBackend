"""Device registration ownership and the push outbox sweep against a real database."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from app.services.notifications import notification_sweeps
from app.services.notifications.sources.push_sender_factory import PushResult
from tests.integration.conftest import login

pytestmark = pytest.mark.asyncio(loop_scope="session")

DEVICES = "/api/v1/me/devices"


class ScriptedSender:
    """Answers per device token the way FCM would; never contacts a provider."""

    def __init__(self, outcomes: dict[str, str]) -> None:
        self.outcomes = outcomes
        self.calls: list[list[str]] = []

    async def send(
        self, push_tokens: list[str], *, title: str, body: str, data: dict[str, Any]
    ) -> PushResult:
        self.calls.append(push_tokens)
        delivered = sum(1 for t in push_tokens if self.outcomes.get(t) == "ok")
        invalid = tuple(t for t in push_tokens if self.outcomes.get(t) == "invalid")
        retryable = any(self.outcomes.get(t) == "retry" for t in push_tokens)
        return PushResult(delivered=delivered, invalid_tokens=invalid, retryable=retryable)


async def _register(client: httpx.AsyncClient, headers: dict[str, str], token: str) -> str:
    response = await client.post(
        DEVICES, json={"platform": "android", "push_token": token}, headers=headers
    )
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


async def _notify(db: asyncpg.Connection, user_id: UUID) -> UUID:
    return await db.fetchval(
        "INSERT INTO notifications (user_id, kind, title, body) "
        "VALUES ($1, 'test', 'Title', 'Body') RETURNING id",
        user_id,
    )


async def _sweep_until_done(
    sender: ScriptedSender, ids: list[UUID], db: asyncpg.Connection
) -> None:
    for _ in range(20):
        await notification_sweeps.deliver_pending_pushes(get_pool())
        pending = await db.fetchval(
            "SELECT count(*) FROM notifications WHERE id = ANY($1::uuid[]) "
            "AND push_status = 'pending'",
            ids,
        )
        if not pending:
            return


async def test_device_removal_is_owner_only(app_client: httpx.AsyncClient) -> None:
    owner = await login(app_client)
    other = await login(app_client)
    device_id = await _register(app_client, owner.headers, f"tok-owner-{uuid4()}")

    stolen = await app_client.delete(f"{DEVICES}/{device_id}", headers=other.headers)
    assert stolen.status_code == 404
    removed = await app_client.delete(f"{DEVICES}/{device_id}", headers=owner.headers)
    assert removed.status_code == 204


async def test_token_moves_to_the_account_that_registers_it_last(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    first = await login(app_client)
    second = await login(app_client)
    token = f"tok-shared-{uuid4()}"
    await _register(app_client, first.headers, token)
    await _register(app_client, second.headers, token)
    owner = await db.fetchval("SELECT user_id FROM user_devices WHERE push_token = $1", token)
    assert owner == second.user_id


async def test_sweep_outcomes(
    app_client: httpx.AsyncClient, db: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivered_user = await login(app_client)
    dead_user = await login(app_client)
    flaky_user = await login(app_client)
    no_device_user = await login(app_client)
    ok_token, dead_token, flaky_token = (
        f"tok-{kind}-{uuid4()}" for kind in ("ok", "dead", "flaky")
    )
    await _register(app_client, delivered_user.headers, ok_token)
    await _register(app_client, dead_user.headers, dead_token)
    await _register(app_client, flaky_user.headers, flaky_token)

    sender = ScriptedSender({ok_token: "ok", dead_token: "invalid", flaky_token: "retry"})
    monkeypatch.setattr(notification_sweeps, "get_push_sender", lambda: sender)
    ids = [
        await _notify(db, delivered_user.user_id),
        await _notify(db, dead_user.user_id),
        await _notify(db, flaky_user.user_id),
        await _notify(db, no_device_user.user_id),
    ]
    await _sweep_until_done(sender, ids, db)

    rows = {
        r["id"]: r
        for r in await db.fetch(
            "SELECT id, push_status, push_attempts FROM notifications WHERE id = ANY($1::uuid[])",
            ids,
        )
    }
    assert rows[ids[0]]["push_status"] == "sent"
    assert rows[ids[1]]["push_status"] == "skipped"
    assert rows[ids[2]]["push_status"] == "failed"
    assert rows[ids[2]]["push_attempts"] == 2
    assert rows[ids[3]]["push_status"] == "skipped"
    assert sum(1 for call in sender.calls if call == [flaky_token]) == 3
    assert sum(1 for call in sender.calls if call == [ok_token]) == 1

    dead_active = await db.fetchval(
        "SELECT is_active FROM user_devices WHERE push_token = $1", dead_token
    )
    assert dead_active is False
