"""apitxt OTP sender: request shape and failure mapping."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest

from app.exceptions.api_errors import ApiError
from app.services.auth.sources import otp_sender_factory
from app.services.auth.sources.otp_sender_factory import ApitxtOtpSender

URL = "https://apitxt.test/api/sendOTP"


def _use(monkeypatch: pytest.MonkeyPatch, handler, **overrides) -> list[httpx.Request]:  # type: ignore[no-untyped-def]
    settings = SimpleNamespace(
        apitxt_auth_key="key-123",
        apitxt_send_otp_url=URL,
        apitxt_channel="sms",
        apitxt_template_id="",
    )
    for name, value in overrides.items():
        setattr(settings, name, value)
    monkeypatch.setattr(otp_sender_factory, "load_settings", lambda: settings)
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        otp_sender_factory.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(record), **kw),
    )
    return seen


async def test_sends_form_with_phone_without_plus(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _use(
        monkeypatch,
        lambda _: httpx.Response(200, json={"status": "success", "message": "sent"}),
        apitxt_template_id="42",
    )
    await ApitxtOtpSender().send("+919876543210", "123456")
    form = parse_qs(seen[0].content.decode())
    assert str(seen[0].url) == URL
    assert form == {
        "authkey": ["key-123"],
        "mobile": ["919876543210"],
        "otp": ["123456"],
        "channel": ["sms"],
        "template_id": ["42"],
    }


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"status": "error", "message": "bad key"}),
        httpx.Response(200, json={"status": "error", "message": "template"}),
        httpx.Response(200, text="not json"),
    ],
)
async def test_provider_failure_is_503(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> None:
    _use(monkeypatch, lambda _: response)
    with pytest.raises(ApiError) as caught:
        await ApitxtOtpSender().send("+919876543210", "123456")
    assert caught.value.status_code == 503
    assert caught.value.code == "otp_send_failed"


def test_missing_key_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, lambda _: httpx.Response(200), apitxt_auth_key="")
    with pytest.raises(ApiError) as caught:
        ApitxtOtpSender().ensure_configured()
    assert caught.value.code == "otp_provider_not_configured"
