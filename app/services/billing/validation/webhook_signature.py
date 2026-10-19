"""HMAC-SHA256 webhook signature check (hex digest of the raw request body)."""

from __future__ import annotations

import hashlib
import hmac


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def signature_matches(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    return hmac.compare_digest(sign_payload(secret, body), signature.strip().lower())
