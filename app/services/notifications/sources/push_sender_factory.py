"""Push delivery providers. FCM / APNs is an OWNER DECISION; console logs in dev."""

from __future__ import annotations

from typing import Any, Protocol

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


def get_push_sender() -> PushSender:
    provider = load_settings().push_provider
    if provider == "console":
        return ConsolePushSender()
    raise RuntimeError(f"PUSH_PROVIDER={provider!r} is not implemented")
