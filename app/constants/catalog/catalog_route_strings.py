"""Catalog (reference data) route constants + static Figma option lists."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_CATALOG

CATALOG_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_CATALOG}"
OPENAPI_TAG_CATALOG: Final[str] = "catalog"

PATH_LANGUAGES: Final[str] = "/languages"
PATH_RATING_TAGS: Final[str] = "/rating-tags"
PATH_PAYMENT_METHODS: Final[str] = "/payment-methods"
PATH_FEE_POLICY: Final[str] = "/fee-policy"

# Figma "Pay for this shift" option list, in display order.
PAYMENT_METHODS: Final[tuple[tuple[str, str], ...]] = (
    ("google_pay", "Google Pay"),
    ("paytm", "Paytm"),
    ("apple_pay", "Apple Pay"),
    ("upi_qr", "Scan UPI QR"),
    ("card_netbanking", "Card / Netbanking"),
)
PAYMENT_METHOD_CODES: Final[frozenset[str]] = frozenset(code for code, _ in PAYMENT_METHODS)

DIRECTION_BUSINESS_TO_WORKER: Final[str] = "business_to_worker"
DIRECTION_WORKER_TO_BUSINESS: Final[str] = "worker_to_business"

# Figma "Rate Aarav" / "How was Café Aroma?" chips.
RATING_TAGS: Final[dict[str, tuple[str, ...]]] = {
    DIRECTION_BUSINESS_TO_WORKER: (
        "On time",
        "Skilled",
        "Professional",
        "Would hire again",
        "Great attitude",
    ),
    DIRECTION_WORKER_TO_BUSINESS: (
        "Paid on time",
        "Clear instructions",
        "Friendly team",
        "Safe workplace",
        "Well organised",
    ),
}

MSG_CATEGORY_UNKNOWN: Final[str] = "Unknown work category."
MSG_BUSINESS_TYPE_UNKNOWN: Final[str] = "Unknown business type."
MSG_NO_ACTIVE_FEE_POLICY: Final[str] = "No active platform fee policy is configured."
