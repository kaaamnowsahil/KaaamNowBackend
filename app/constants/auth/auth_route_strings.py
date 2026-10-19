"""Auth route + message constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_AUTH

AUTH_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_AUTH}"
OPENAPI_TAG_AUTH: Final[str] = "auth"

PATH_OTP_SEND: Final[str] = "/otp/send"
PATH_OTP_VERIFY: Final[str] = "/otp/verify"
PATH_TOKEN_REFRESH: Final[str] = "/token/refresh"
PATH_LOGOUT: Final[str] = "/logout"

TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_TYPE_BEARER: Final[str] = "bearer"
PHONE_E164_PATTERN: Final[str] = r"^\+[1-9]\d{7,14}$"

DESC_SWAGGER_BEARER: Final[str] = (
    "Access token from POST /api/v1/auth/otp/verify (OTP is printed to the API log in dev)."
)

MSG_AUTHENTICATION_REQUIRED: Final[str] = "Authentication required."
MSG_TOKEN_EXPIRED: Final[str] = "Access token expired. Refresh and retry."
MSG_TOKEN_INVALID: Final[str] = "Invalid access token."
MSG_PERMISSION_DENIED: Final[str] = "You do not have permission for this action."
MSG_INVALID_PHONE: Final[str] = "Phone number must be in E.164 format, e.g. +919876543210."
MSG_OTP_RATE_LIMITED: Final[str] = "Too many OTP requests. Try again later."
MSG_OTP_COOLDOWN: Final[str] = "Please wait before requesting another OTP."
MSG_OTP_INVALID: Final[str] = "Invalid or expired OTP."
MSG_OTP_ATTEMPTS_EXCEEDED: Final[str] = "Too many attempts. Request a new OTP."
MSG_ACCOUNT_DISABLED: Final[str] = "This account is disabled."
MSG_REFRESH_INVALID: Final[str] = "Invalid or expired refresh token."
MSG_REFRESH_REUSED: Final[str] = "Refresh token reuse detected; please sign in again."
