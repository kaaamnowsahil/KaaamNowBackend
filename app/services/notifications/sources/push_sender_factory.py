"""Push delivery providers: console logs in dev, FCM HTTP v1 in production."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt

from app.config.settings import load_settings
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)


@dataclass(frozen=True)
class PushResult:
    """Provider outcome for one notification fanned out to a user's devices."""

    delivered: int = 0
    invalid_tokens: tuple[str, ...] = ()
    retryable: bool = False


class PushSender(Protocol):
    async def send(
        self, push_tokens: list[str], *, title: str, body: str, data: dict[str, Any]
    ) -> PushResult:
        """``delivered`` counts devices whose message the provider accepted."""
        ...


class ConsolePushSender:
    """Logs instead of delivering. In production nothing reaches a device, so the push is
    reported as not accepted (``failed``) rather than ``sent``."""

    async def send(
        self, push_tokens: list[str], *, title: str, body: str, data: dict[str, Any]
    ) -> PushResult:
        log.info(
            "push (console provider)",
            extra=log_extra(devices=len(push_tokens), kind=data.get("kind")),
        )
        if load_settings().is_production:
            return PushResult()
        return PushResult(delivered=len(push_tokens))


FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCESS_TOKEN_TTL_SECONDS = 3600
ACCESS_TOKEN_REFRESH_MARGIN_SECONDS = 300


class FcmPushSender:
    """One HTTP v1 request per device (v1 has no multicast). Access tokens are minted from
    the service account and cached until shortly before expiry."""

    def __init__(self, service_account_file: str, project_id: str) -> None:
        account = json.loads(Path(service_account_file).read_text())
        self._client_email: str = account["client_email"]
        self._private_key: str = account["private_key"]
        self._token_uri: str = account.get("token_uri", GOOGLE_TOKEN_URL)
        self._project = project_id or account["project_id"]
        self._access_token = ""
        self._expires_at = 0.0

    async def _token(self, client: httpx.AsyncClient) -> str:
        now = time.time()
        if self._access_token and now < self._expires_at - ACCESS_TOKEN_REFRESH_MARGIN_SECONDS:
            return self._access_token
        assertion = jwt.encode(
            {
                "iss": self._client_email,
                "scope": FCM_SCOPE,
                "aud": self._token_uri,
                "iat": int(now),
                "exp": int(now) + ACCESS_TOKEN_TTL_SECONDS,
            },
            self._private_key,
            algorithm="RS256",
        )
        response = await client.post(
            self._token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        response.raise_for_status()
        body = response.json()
        self._access_token = body["access_token"]
        self._expires_at = now + int(body.get("expires_in", ACCESS_TOKEN_TTL_SECONDS))
        return self._access_token

    async def send(
        self, push_tokens: list[str], *, title: str, body: str, data: dict[str, Any]
    ) -> PushResult:
        payload_data = {k: str(v) for k, v in data.items() if v is not None}
        delivered = 0
        invalid: list[str] = []
        retryable = False
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                token = await self._token(client)
            except (httpx.HTTPError, jwt.PyJWTError, KeyError, ValueError) as exc:
                log.warning("fcm auth failed", extra=log_extra(error=type(exc).__name__))
                return PushResult(retryable=True)
            for device in push_tokens:
                try:
                    response = await client.post(
                        FCM_SEND_URL.format(project=self._project),
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "message": {
                                "token": device,
                                "notification": {"title": title, "body": body},
                                "data": payload_data,
                                "android": {"priority": "high"},
                            }
                        },
                    )
                except httpx.HTTPError as exc:
                    log.warning("fcm send error", extra=log_extra(error=type(exc).__name__))
                    retryable = True
                    continue
                if response.is_success:
                    delivered += 1
                    continue
                outcome = classify_fcm_error(response)
                log.warning(
                    "fcm send rejected",
                    extra=log_extra(status=response.status_code, outcome=outcome),
                )
                if outcome == FCM_INVALID_TOKEN:
                    invalid.append(device)
                elif outcome == FCM_RETRYABLE:
                    retryable = True
        return PushResult(delivered=delivered, invalid_tokens=tuple(invalid), retryable=retryable)


FCM_INVALID_TOKEN = "invalid_token"
FCM_RETRYABLE = "retryable"
FCM_REJECTED = "rejected"
_FCM_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _fcm_error_code(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return ""
    for detail in error.get("details", []) or []:
        code = detail.get("errorCode") if isinstance(detail, dict) else None
        if code:
            return str(code)
    return str(error.get("status", ""))


def classify_fcm_error(response: httpx.Response) -> str:
    """Map an FCM HTTP v1 error to: drop the token, retry later, or give up on this message.

    Only provider codes are inspected; the response body is never logged because it can echo
    the device token.
    """
    code = _fcm_error_code(response)
    if code in {"UNREGISTERED", "SENDER_ID_MISMATCH"} or response.status_code == 404:
        return FCM_INVALID_TOKEN
    if code == "INVALID_ARGUMENT" and "token" in response.text.lower():
        return FCM_INVALID_TOKEN
    if code in {"UNAVAILABLE", "INTERNAL", "QUOTA_EXCEEDED"}:
        return FCM_RETRYABLE
    if response.status_code in _FCM_RETRYABLE_STATUSES:
        return FCM_RETRYABLE
    return FCM_REJECTED


_fcm_sender: FcmPushSender | None = None


def get_push_sender() -> PushSender:
    global _fcm_sender
    settings = load_settings()
    provider = settings.push_provider
    if provider == "console":
        return ConsolePushSender()
    if provider == "fcm":
        if _fcm_sender is None:
            if not settings.firebase_service_account_file:
                raise RuntimeError("PUSH_PROVIDER=fcm needs FIREBASE_SERVICE_ACCOUNT_FILE")
            _fcm_sender = FcmPushSender(
                settings.firebase_service_account_file, settings.firebase_project_id
            )
        return _fcm_sender
    raise RuntimeError(f"PUSH_PROVIDER={provider!r} is not implemented")


def push_delivery_status() -> str:
    """``fcm`` when FCM credentials load, ``console`` when pushes are only logged.

    Raises when ``PUSH_PROVIDER=fcm`` is set but the service account is missing or malformed,
    so a misconfigured deploy fails at startup instead of silently dropping pushes.
    """
    provider = load_settings().push_provider
    try:
        get_push_sender()
    except (OSError, KeyError, ValueError) as exc:
        raise RuntimeError(
            f"PUSH_PROVIDER=fcm: service account could not be loaded ({type(exc).__name__})"
        ) from exc
    return provider
