"""Human-readable references shown on receipts (``KN-48213``, ``WD-20931``)."""

from __future__ import annotations

import secrets

PAYMENT_REFERENCE_PREFIX = "KN"
WITHDRAWAL_REFERENCE_PREFIX = "WD"
INVOICE_REFERENCE_PREFIX = "INV"


def new_reference(prefix: str, digits: int = 8) -> str:
    """Random numeric reference. Uniqueness is enforced by a DB unique constraint."""
    number = secrets.randbelow(10**digits)
    return f"{prefix}-{number:0{digits}d}"


def new_numeric_code(length: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))
