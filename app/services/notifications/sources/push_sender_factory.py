"""Push delivery providers: console logs in dev, FCM HTTP v1 in production."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt

from app.config.settings import load_settings
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)


class PushSender(Protocol):
    async def send(
        self, push_tokens: list[str], *, title: str, body: str, data: dict[str, Any]
    ) -> bool:
        """Return True when the provider accepted the message."""
        ...


class ConsolePushSender:
    async def send(
        self, push_tokens: list[str], *, title: str, body: str, data: dict[str, Any]
    ) -> bool:
        log.info(
            "push (console provider)",
            extra=log_extra(devices=len(push_tokens), title=title, kind=data.get("kind")),
        )
        return True


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
    ) -> bool:
        payload_data = {k: str(v) for k, v in data.items() if v is not None}
        delivered = False
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                token = await self._token(client)
            except httpx.HTTPError as exc:
                log.warning("fcm auth failed", extra=log_extra(error=str(exc)))
                return False
            for device in push_tokens:
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
                if response.is_success:
                    delivered = True
                else:
                    log.warning(
                        "fcm send failed",
                        extra=log_extra(status=response.status_code, body=response.text[:300]),
                    )
        return delivered


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
