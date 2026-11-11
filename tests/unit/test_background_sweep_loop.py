from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import pytest

from app.services.background import background_sweep_loop


class _Conn:
    def __init__(self, unlock_error: BaseException | None) -> None:
        self.unlock_error = unlock_error
        self.terminated = False

    async def fetchval(self, *_: Any) -> bool:
        return True

    async def execute(self, *_: Any) -> None:
        if self.unlock_error is not None:
            raise self.unlock_error

    def terminate(self) -> None:
        self.terminated = True
        raise asyncpg.InterfaceError("connection has been released back to the pool")


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


@pytest.fixture(autouse=True)
def _no_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(background_sweep_loop, "_jobs", lambda: [])


async def test_lost_connection_during_unlock_is_not_raised() -> None:
    conn = _Conn(asyncpg.InterfaceError("connection is closed"))

    await background_sweep_loop.run_locked_sweep(_Pool(conn))  # type: ignore[arg-type]

    assert conn.terminated


async def test_other_unlock_failures_still_raise() -> None:
    conn = _Conn(RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await background_sweep_loop.run_locked_sweep(_Pool(conn))  # type: ignore[arg-type]

    assert conn.terminated
