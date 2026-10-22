"""Password hashing helpers using a versioned PBKDF2-SHA256 format."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 600_000
_SALT_BYTES = 16
_DUMMY_PASSWORD_HASH = f"pbkdf2_sha256${_ITERATIONS}${'00' * _SALT_BYTES}${'00' * 32}"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def burn_password_check(password: str) -> None:
    """Perform a comparable hash operation when the account has no password hash."""
    verify_password(password, _DUMMY_PASSWORD_HASH)
