"""Phone normalisation and OTP hashing (pure functions — unit tested)."""

from __future__ import annotations

import hashlib
import hmac
import re

from app.constants.auth.auth_route_strings import MSG_INVALID_PHONE, PHONE_E164_PATTERN
from app.exceptions.api_errors import bad_request

_PHONE_RE = re.compile(PHONE_E164_PATTERN)
_PHONE_STRIP_RE = re.compile(r"[\s\-()]")


def normalize_phone(phone: str) -> str:
    cleaned = _PHONE_STRIP_RE.sub("", phone or "")
    if not _PHONE_RE.match(cleaned):
        raise bad_request("invalid_phone", MSG_INVALID_PHONE)
    return cleaned


def hash_otp_code(secret: str, phone: str, code: str) -> str:
    """HMAC-SHA256 keyed by the server secret, bound to the phone number."""
    return hmac.new(secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def otp_code_matches(secret: str, phone: str, code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp_code(secret, phone, code), expected_hash)
