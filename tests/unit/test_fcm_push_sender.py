"""FCM HTTP v1 sender against a mocked transport; the service account is a throwaway key."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import load_settings
from app.services.notifications.sources import push_sender_factory as factory


@pytest.fixture
def service_account(tmp_path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    path = tmp_path / "sa.json"
    path.write_text(
        json.dumps(
            {
                "client_email": "push@unit-test.iam.gserviceaccount.com",
                "private_key": pem,
                "project_id": "unit-test",
                "token_uri": "https://oauth2.test/token",
            }
        )
    )
    return path


def _fcm_error(status: int, code: str, message: str = "") -> httpx.Response:
    detail = [{"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": code}]
    return httpx.Response(
        status,
        json={"error": {"code": status, "status": code, "message": message, "details": detail}},
    )


def _mock_client(
    monkeypatch: pytest.MonkeyPatch, by_token: dict[str, httpx.Response]
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.test":
            return httpx.Response(200, json={"access_token": "ya29.unit", "expires_in": 3600})
        message = json.loads(request.content)["message"]
        sent.append(message)
        outcome = by_token[message["token"]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        factory.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return sent


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_fcm_error(404, "UNREGISTERED"), factory.FCM_INVALID_TOKEN),
        (_fcm_error(403, "SENDER_ID_MISMATCH"), factory.FCM_INVALID_TOKEN),
        (
            _fcm_error(400, "INVALID_ARGUMENT", "The registration token is not valid"),
            factory.FCM_INVALID_TOKEN,
        ),
        (_fcm_error(400, "INVALID_ARGUMENT", "Invalid JSON payload"), factory.FCM_REJECTED),
        (_fcm_error(429, "QUOTA_EXCEEDED"), factory.FCM_RETRYABLE),
        (_fcm_error(503, "UNAVAILABLE"), factory.FCM_RETRYABLE),
        (httpx.Response(502, text="bad gateway"), factory.FCM_RETRYABLE),
        (_fcm_error(401, "THIRD_PARTY_AUTH_ERROR"), factory.FCM_REJECTED),
    ],
)
def test_classify_fcm_error(response: httpx.Response, expected: str) -> None:
    assert factory.classify_fcm_error(response) == expected


async def test_fcm_send_reports_each_device_outcome(
    service_account: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _mock_client(
        monkeypatch,
        {
            "good": httpx.Response(200, json={"name": "projects/unit-test/messages/1"}),
            "gone": _fcm_error(404, "UNREGISTERED"),
            "busy": _fcm_error(503, "UNAVAILABLE"),
            "net": httpx.ConnectError("down"),  # type: ignore[dict-item]
        },
    )
    sender = factory.FcmPushSender(str(service_account), "")
    result = await sender.send(
        ["good", "gone", "busy", "net"], title="Hi", body="There", data={"kind": "k", "x": None}
    )
    assert result == factory.PushResult(delivered=1, invalid_tokens=("gone",), retryable=True)
    assert sent[0]["data"] == {"kind": "k"}
    assert sent[0]["notification"] == {"title": "Hi", "body": "There"}


async def test_fcm_never_reports_sent_when_every_device_fails(
    service_account: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_client(monkeypatch, {"gone": _fcm_error(404, "UNREGISTERED")})
    result = await factory.FcmPushSender(str(service_account), "p").send(
        ["gone"], title="T", body="B", data={}
    )
    assert result.delivered == 0 and result.invalid_tokens == ("gone",)


async def test_fcm_auth_failure_is_retryable_not_sent(
    service_account: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        factory.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(400, json={"error": "invalid_grant"})
            ),
            **kwargs,
        ),
    )
    result = await factory.FcmPushSender(str(service_account), "p").send(
        ["t"], title="T", body="B", data={}
    )
    assert result == factory.PushResult(retryable=True)


def test_push_status_reports_console_when_fcm_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(load_settings(), "push_provider", "console")
    assert factory.push_delivery_status() == "console"


def test_fcm_without_credentials_fails_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = load_settings()
    monkeypatch.setattr(factory, "_fcm_sender", None)
    monkeypatch.setattr(settings, "push_provider", "fcm")
    monkeypatch.setattr(settings, "firebase_service_account_file", "")
    with pytest.raises(RuntimeError, match="FIREBASE_SERVICE_ACCOUNT_FILE"):
        factory.push_delivery_status()

    monkeypatch.setattr(settings, "firebase_service_account_file", str(tmp_path / "missing.json"))
    with pytest.raises(RuntimeError, match="could not be loaded"):
        factory.push_delivery_status()

    broken = tmp_path / "broken.json"
    broken.write_text('{"project_id": "p"}')
    monkeypatch.setattr(settings, "firebase_service_account_file", str(broken))
    with pytest.raises(RuntimeError, match="could not be loaded"):
        factory.push_delivery_status()


def test_fcm_with_valid_credentials_is_reported(
    monkeypatch: pytest.MonkeyPatch, service_account: Path
) -> None:
    settings = load_settings()
    monkeypatch.setattr(factory, "_fcm_sender", None)
    monkeypatch.setattr(settings, "push_provider", "fcm")
    monkeypatch.setattr(settings, "firebase_service_account_file", str(service_account))
    assert factory.push_delivery_status() == "fcm"


def test_unknown_push_provider_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_settings(), "push_provider", "apns")
    with pytest.raises(RuntimeError, match="not implemented"):
        factory.get_push_sender()
