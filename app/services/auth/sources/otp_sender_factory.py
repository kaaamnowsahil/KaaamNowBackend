"""Development-only console OTP sender."""

from __future__ import annotations

from typing import Protocol

from app.config.settings import load_settings
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)


class OtpSender(Protocol):
    def ensure_configured(self) -> None: ...

    async def send(self, phone: str, code: str) -> None: ...


class ConsoleOtpSender:
    def ensure_configured(self) -> None:
        return None

    async def send(self, phone: str, code: str) -> None:
        log.warning("DEV OTP (console provider)", extra=log_extra(phone=phone, otp_code=code))


_SENDERS: dict[str, type] = {"console": ConsoleOtpSender}


def get_otp_sender() -> OtpSender:
    provider = load_settings().otp_provider
    sender_cls = _SENDERS.get(provider)
    if sender_cls is None:
        raise RuntimeError(f"unknown OTP_PROVIDER: {provider}")
    return sender_cls()
