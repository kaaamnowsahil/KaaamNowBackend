"""Auth route + message constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_AUTH

AUTH_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_AUTH}"
OPENAPI_TAG_AUTH: Final[str] = "auth"

PATH_OTP_SEND: Final[str] = "/otp/send"
PATH_OTP_VERIFY: Final[str] = "/otp/verify"
PATH_FIREBASE_VERIFY: Final[str] = "/firebase/verify"
PATH_SIGNUP: Final[str] = "/signup"
PATH_PHONE_CHECK: Final[str] = "/phone/check"

INTENT_SIGN_IN: Final[str] = "sign_in"
INTENT_SIGN_UP: Final[str] = "sign_up"
PATH_TOKEN_REFRESH: Final[str] = "/token/refresh"
PATH_LOGOUT: Final[str] = "/logout"

TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_TYPE_BEARER: Final[str] = "bearer"
PHONE_E164_PATTERN: Final[str] = r"^\+[1-9]\d{7,14}$"

OTP_PROVIDER_FIREBASE: Final[str] = "firebase"
FIREBASE_JWKS_URL: Final[str] = (
    "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
)
FIREBASE_ISSUER_PREFIX: Final[str] = "https://securetoken.google.com/"
FIREBASE_SIGNING_ALGORITHM: Final[str] = "RS256"
FIREBASE_JWKS_DEFAULT_TTL_SECONDS: Final[int] = 3600
FIREBASE_JWKS_TIMEOUT_SECONDS: Final[float] = 10.0

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
MSG_FIREBASE_NOT_CONFIGURED: Final[str] = "Firebase sign-in is not configured on this server."
MSG_FIREBASE_TOKEN_INVALID: Final[str] = "Invalid or expired Firebase sign-in token."
MSG_FIREBASE_PHONE_MISSING: Final[str] = "Firebase token has no verified phone number."
MSG_FIREBASE_UNAVAILABLE: Final[str] = "Could not reach Firebase to verify sign-in. Try again."
MSG_OTP_SENT_BY_FIREBASE: Final[str] = "OTP is sent by Firebase; use POST /auth/firebase/verify."
MSG_ACCOUNT_NOT_FOUND: Final[str] = "No account found for this number. Create an account first."
MSG_PHONE_REGISTERED: Final[str] = "This number already has an account. Log in instead."
MSG_ROLE_NOT_REGISTERED: Final[str] = "This number has no {role} account. Create one first."
MSG_ROLE_REGISTERED: Final[str] = "This number already has a {role} account. Log in instead."
MSG_SIGNUP_IDENTITY: Final[str] = "Send either phone + code (SMS OTP) or id_token (Firebase)."
MSG_SIGNUP_DETAILS: Final[str] = "Send the details block that matches the chosen role."
