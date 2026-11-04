"""Production hides the API map, and every response carries browser hardening headers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config.settings import KaaamNowSettings, load_settings
from app.kaaamnow_api_server import create_kaaamnow_api_application

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def _client() -> TestClient:
    return TestClient(create_kaaamnow_api_application(), raise_server_exceptions=False)


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(KaaamNowSettings, "is_production", property(lambda _self: True))
    monkeypatch.setattr(load_settings(), "api_docs_enabled", None)


def test_docs_are_hidden_in_production(production) -> None:  # type: ignore[no-untyped-def]
    client = _client()
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404, path
    assert "docs" not in client.get("/").json()


def test_docs_can_be_turned_back_on_in_production(production, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(load_settings(), "api_docs_enabled", True)
    assert _client().get("/openapi.json").status_code == 200


def test_docs_are_served_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(KaaamNowSettings, "is_production", property(lambda _self: False))
    monkeypatch.setattr(load_settings(), "api_docs_enabled", None)
    client = _client()
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/").json()["docs"] == "/docs"


@pytest.mark.parametrize("path", ["/", "/api/v1/notifications", "/no-such-route"])
def test_every_response_has_security_headers(path: str) -> None:
    resp = _client().get(path)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert resp.headers["referrer-policy"] == "no-referrer"


def test_notifications_require_sign_in() -> None:
    client = _client()
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401
    assert client.post("/api/v1/notifications/read-all").status_code == 401
    assert client.post("/api/v1/me/devices", json={}).status_code == 401
