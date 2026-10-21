"""Business / worker profile + admin verification route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import (
    API_V1,
    SEGMENT_ADMIN,
    SEGMENT_BUSINESS,
    SEGMENT_WORKER,
    SEGMENT_WORKERS,
)

BUSINESS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_BUSINESS}"
WORKER_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKER}"
WORKERS_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKERS}"
ADMIN_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ADMIN}"

OPENAPI_TAG_BUSINESS_PROFILE: Final[str] = "business profile"
OPENAPI_TAG_WORKER_PROFILE: Final[str] = "worker profile"
OPENAPI_TAG_ADMIN: Final[str] = "admin"

PATH_PROFILE: Final[str] = "/profile"
PATH_PROFILE_LOGO: Final[str] = "/profile/logo"
LOGO_STORAGE_FOLDER: Final[str] = "logos"
PATH_AVAILABILITY: Final[str] = "/availability"
PATH_LOCATION: Final[str] = "/location"
PATH_WORKER_BY_ID: Final[str] = "/{worker_profile_id}"
PATH_ADMIN_VERIFICATIONS: Final[str] = "/verifications"
PATH_ADMIN_WORKER_VERIFICATION: Final[str] = "/workers/{worker_profile_id}/verification"
PATH_ADMIN_BUSINESS_VERIFICATION: Final[str] = "/businesses/{business_profile_id}/verification"

VERIFICATION_PENDING: Final[str] = "pending"
VERIFICATION_VERIFIED: Final[str] = "verified"
VERIFICATION_REJECTED: Final[str] = "rejected"

MSG_BUSINESS_PROFILE_MISSING: Final[str] = "Add the Business role first (POST /api/v1/me/roles)."
MSG_WORKER_PROFILE_MISSING: Final[str] = "Add the Worker role first (POST /api/v1/me/roles)."
MSG_WORKER_NOT_FOUND: Final[str] = "Worker not found."
MSG_BUSINESS_NOT_FOUND: Final[str] = "Business not found."
MSG_BUSINESS_PROFILE_INCOMPLETE: Final[str] = (
    "Complete your business name and location before posting shifts."
)
MSG_WORKER_NOT_VERIFIED: Final[str] = "Your worker profile is awaiting verification."
MSG_WORKER_LOCATION_REQUIRED: Final[str] = "Share your location to go online."
MSG_COORDINATES_PAIR: Final[str] = "Latitude and longitude must be sent together."
