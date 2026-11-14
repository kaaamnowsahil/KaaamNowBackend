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


RING_LANGUAGES = frozenset(
    {"bn", "en", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te", "ur"}
)
ALERTS_CHANNEL = "kaaamnow_alerts"
# Silent banner only. The spoken file is played by the app, not by this channel.
VOICE_CHANNEL = "kaaamnow_voice"
# Pre-created on the phone with the raw file on the alarm stream. A background or
# killed app never runs our player, so the system must play this channel's sound.
ALARM_CHANNEL_PREFIX = "kaaamnow_alarm_"


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def android_channel(
    kind: object, language: object, data: dict[str, Any] | None = None
) -> tuple[str, str | None]:
    """Channel id, and the raw sound name the app plays itself for a spoken ring.

    ``live_request`` is the worker's new-work line. The business "finding Workers" note uses
    the same kind with ``live_work`` and stays a plain alert. ``live_worker_accepted`` is the
    business's worker-accepted line. The banner uses the alarm channel whose sound is the
    spoken file, so a background phone still rings. ``data.sound`` lets the open app play
    the same file itself.
    """
    lang = language if isinstance(language, str) and language in RING_LANGUAGES else "en"
    payload = data or {}
    if kind == "live_request" and not _truthy(payload.get("live_work")):
        sound = f"ring_{lang}_new_work"
        return f"{ALARM_CHANNEL_PREFIX}{sound}", sound
    if kind == "live_worker_accepted":
        sound = f"ring_{lang}_worker_accepted"
        return f"{ALARM_CHANNEL_PREFIX}{sound}", sound
    return ALERTS_CHANNEL, None


def _fcm_message(
    *,
    token: str,
    title: str,
    body: str,
    data: dict[str, Any],
    payload_data: dict[str, str],
    language: str | None,
    platform: str | None,
) -> dict[str, Any]:
    """The banner is a normal FCM notification. Spoken rings use the alarm channel that
    already points at the raw file, and repeat that filename in ``data.sound`` for the
    open app. A ``sound`` field on the FCM notification itself makes Android play the
    phone's default tone, so it is left off.
    """
    _ = platform
    channel_id, sound = android_channel(data.get("kind"), language, data)
    delivered = dict(payload_data)
    if sound:
        delivered["sound"] = sound
    return {
        "token": token,
        "notification": {"title": title, "body": body},
        "data": delivered,
        "android": {
            "priority": "high",
            "notification": {
                "channel_id": channel_id,
                "notification_priority": "PRIORITY_HIGH",
            },
        },
        # iOS shows a background push silently unless aps names a sound.
        "apns": {
            "headers": {"apns-priority": "10"},
            "payload": {"aps": {"sound": "default"}},
        },
        "webpush": {"headers": {"Urgency": "high"}},
    }


class PushSender(Protocol):
    async def send(
        self,
        push_tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, Any],
        language: str | None = None,
        platforms: list[str] | None = None,
    ) -> PushResult:
        """``delivered`` counts devices whose message the provider accepted."""
        ...


class ConsolePushSender:
    """Logs instead of delivering. In production nothing reaches a device, so the push is
    reported as not accepted (``failed``) rather than ``sent``."""

    async def send(
        self,
        push_tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, Any],
        language: str | None = None,
        platforms: list[str] | None = None,
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

    def __init__(self, account: dict[str, Any], project_id: str) -> None:
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
        self,
        push_tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, Any],
        language: str | None = None,
        platforms: list[str] | None = None,
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
            for index, device in enumerate(push_tokens):
                platform = platforms[index] if platforms and index < len(platforms) else None
                try:
                    response = await client.post(
                        FCM_SEND_URL.format(project=self._project),
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "message": _fcm_message(
                                token=device,
                                title=title,
                                body=body,
                                data=data,
                                payload_data=payload_data,
                                language=language,
                                platform=platform,
                            )
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


def _service_account() -> dict[str, Any]:
    settings = load_settings()
    if settings.firebase_service_account_json:
        return json.loads(settings.firebase_service_account_json)
    if settings.firebase_service_account_file:
        return json.loads(Path(settings.firebase_service_account_file).read_text())
    raise RuntimeError(
        "PUSH_PROVIDER=fcm needs FIREBASE_SERVICE_ACCOUNT_FILE or FIREBASE_SERVICE_ACCOUNT_JSON"
    )


def get_push_sender() -> PushSender:
    global _fcm_sender
    settings = load_settings()
    provider = settings.push_provider
    if provider == "console":
        return ConsolePushSender()
    if provider == "fcm":
        if _fcm_sender is None:
            _fcm_sender = FcmPushSender(_service_account(), settings.firebase_project_id)
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
