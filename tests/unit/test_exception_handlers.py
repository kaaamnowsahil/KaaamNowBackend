from __future__ import annotations

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exceptions.exception_handlers import register_exception_handlers


@pytest.mark.parametrize(
    "exc",
    [
        asyncpg.exceptions.ConnectionDoesNotExistError("closed in the middle of operation"),
        ConnectionResetError(54, "Connection reset by peer"),
        TimeoutError(),
    ],
)
def test_lost_database_connection_is_a_clean_503(exc: Exception) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    resp = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert resp.status_code == 503
    assert resp.json()["code"] == "database_unavailable"
