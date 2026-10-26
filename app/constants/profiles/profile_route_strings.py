"""Business / Work and worker profile + admin verification route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ADMIN

ADMIN_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ADMIN}"

OPENAPI_TAG_ADMIN: Final[str] = "admin - verification"

PATH_ADMIN_VERIFICATIONS: Final[str] = "/verifications"
PATH_ADMIN_WORKER_VERIFICATION: Final[str] = "/workers/{worker_profile_id}/verification"
PATH_ADMIN_BUSINESS_VERIFICATION: Final[str] = "/businesses/{business_profile_id}/verification"

VERIFICATION_PENDING: Final[str] = "pending"
VERIFICATION_VERIFIED: Final[str] = "verified"
VERIFICATION_REJECTED: Final[str] = "rejected"

MAX_BUSINESS_ENTITIES: Final[int] = 50
MAX_BUSINESS_TYPES: Final[int] = 10

MSG_BUSINESS_TYPE_REQUIRED: Final[str] = "Choose at least one Business / Work type."

MSG_BUSINESS_PROFILE_MISSING: Final[str] = (
    "Sign up as a Business / Work account first (POST /api/v1/auth/signup)."
)
MSG_WORKER_PROFILE_MISSING: Final[str] = "Sign up as a Worker first (POST /api/v1/auth/signup)."
MSG_WORKER_NOT_FOUND: Final[str] = "Worker not found."
MSG_BUSINESS_NOT_FOUND: Final[str] = "Business / Work profile not found."
MSG_BUSINESS_PROFILE_INCOMPLETE: Final[str] = (
    "Complete your Business / Work name before posting shifts."
)
MSG_BUSINESS_LIMIT_REACHED: Final[str] = (
    "You have reached the maximum number of Business / Work profiles."
)
MSG_WORKER_NOT_VERIFIED: Final[str] = "Your worker profile is awaiting verification."
MSG_WORKER_BANNED: Final[str] = (
    "Your worker account is on hold after repeated strikes. Contact support."
)
MSG_WORKER_LOCATION_REQUIRED: Final[str] = "Share your location to go online."
MSG_COORDINATES_PAIR: Final[str] = "Latitude and longitude must be sent together."
