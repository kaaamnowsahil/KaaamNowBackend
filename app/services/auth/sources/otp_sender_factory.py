"""OTP delivery: console (development) or apitxt (SMS / WhatsApp / voice)."""

from __future__ import annotations

from typing import Protocol

import httpx
from fastapi import status

from app.config.settings import load_settings
from app.constants.auth.auth_route_strings import (
    APITXT_TIMEOUT_SECONDS,
    MSG_OTP_PROVIDER_NOT_CONFIGURED,
    MSG_OTP_SEND_FAILED,
    OTP_PROVIDER_APITXT,
    OTP_PROVIDER_CONSOLE,
)
from app.exceptions.api_errors import ApiError
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


class ApitxtOtpSender:
    """POST /api/sendOTP; apitxt only delivers the code, verification stays on our side."""

    def ensure_configured(self) -> None:
        if not load_settings().apitxt_auth_key:
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "otp_provider_not_configured",
                MSG_OTP_PROVIDER_NOT_CONFIGURED,
            )

    async def send(self, phone: str, code: str) -> None:
        settings = load_settings()
        form = {
            "authkey": settings.apitxt_auth_key,
            "mobile": phone.lstrip("+"),
            "otp": code,
            "channel": settings.apitxt_channel,
        }
        if settings.apitxt_template_id:
            form["template_id"] = settings.apitxt_template_id
        try:
            async with httpx.AsyncClient(timeout=APITXT_TIMEOUT_SECONDS) as client:
                response = await client.post(settings.apitxt_send_otp_url, data=form)
            body = response.json() if response.content else {}
        except (httpx.HTTPError, ValueError) as exc:
            log.error("apitxt OTP request failed", extra=log_extra(error=str(exc)))
            raise _send_failed() from exc
        if response.status_code != status.HTTP_200_OK or body.get("status") != "success":
            log.error(
                "apitxt OTP rejected",
                extra=log_extra(
                    http_status=response.status_code, provider_message=body.get("message")
                ),
            )
            raise _send_failed()


def _send_failed() -> ApiError:
    return ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, "otp_send_failed", MSG_OTP_SEND_FAILED)


_SENDERS: dict[str, type] = {
    OTP_PROVIDER_CONSOLE: ConsoleOtpSender,
    OTP_PROVIDER_APITXT: ApitxtOtpSender,
}


def get_otp_sender() -> OtpSender:
    provider = load_settings().otp_provider
    sender_cls = _SENDERS.get(provider)
    if sender_cls is None:
        raise RuntimeError(f"unknown OTP_PROVIDER: {provider}")
    return sender_cls()
