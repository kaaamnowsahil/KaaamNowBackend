"""Promo code route constants (business posting, worker wallet)."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_BUSINESS, SEGMENT_WORKER

BUSINESS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_BUSINESS}"
WORKER_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKER}"
OPENAPI_TAG_PROMOS: Final[str] = "promo codes"

PATH_PROMO_CODES: Final[str] = "/promo-codes"
PATH_PROMO_VALIDATE: Final[str] = "/promo-codes/validate"
PATH_PROMO_REDEEM: Final[str] = "/promo-codes/redeem"

PROMO_CODE_MAX_LENGTH: Final[int] = 32
ENTRY_PROMO_CREDIT: Final[str] = "promo_credit"

MSG_PROMO_INVALID: Final[dict[str, str]] = {
    "not_found": "That promo code doesn't exist.",
    "wrong_role": "That promo code isn't for this account type.",
    "not_started": "That promo code isn't active yet.",
    "expired": "That promo code has expired.",
    "used_up": "That promo code has been fully used.",
    "already_used": "You've already used this promo code.",
}
MSG_PROMO_PENDING: Final[str] = "You already have a promo code waiting for your next payout."
