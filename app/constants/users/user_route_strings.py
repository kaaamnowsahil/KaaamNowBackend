"""Current-user (/me) route + message constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ME

ME_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ME}"
OPENAPI_TAG_ME: Final[str] = "me"

PATH_PROFILE: Final[str] = "/profile"
PATH_PROFILE_IMAGE: Final[str] = "/profile/image"
PATH_AVAILABILITY: Final[str] = "/availability"
PATH_LOCATION: Final[str] = "/location"
PATH_WORKER_BY_ID: Final[str] = "/workers/{worker_profile_id}"
PATH_BUSINESSES: Final[str] = "/businesses"
PATH_BUSINESS: Final[str] = "/businesses/{business_profile_id}"
PATH_BUSINESS_LOGO: Final[str] = "/businesses/{business_profile_id}/logo"
PATH_DEVICES: Final[str] = "/devices"
PATH_ACTIVE_ROLE: Final[str] = "/active-role"
PATH_ROLES: Final[str] = "/roles"
PATH_DEVICE: Final[str] = "/devices/{device_id}"
PATH_DELETION_REQUESTS: Final[str] = "/deletion-requests"
PATH_CURRENT_DELETION_REQUEST: Final[str] = "/deletion-requests/current"

THEME_PREFERENCES: Final[tuple[str, ...]] = ("system", "light", "dark")
DEVICE_PLATFORMS: Final[tuple[str, ...]] = ("ios", "android", "web")
ALLOWED_PHOTO_CONTENT_TYPES: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
AVATAR_STORAGE_FOLDER: Final[str] = "avatars"
LOGO_STORAGE_FOLDER: Final[str] = "logos"

MSG_USER_NOT_FOUND: Final[str] = "User not found."
MSG_ROLE_NOT_SELF_SERVICE: Final[str] = "This role cannot be added from the app."
MSG_LANGUAGE_UNKNOWN: Final[str] = "Unknown or inactive language."
MSG_PHOTO_TYPE: Final[str] = "Photo must be JPEG, PNG or WebP."
MSG_PHOTO_TOO_LARGE: Final[str] = "Photo is larger than the allowed size."
MSG_PHOTO_CONTENT: Final[str] = "File contents do not match a JPEG, PNG or WebP image."
MSG_DEVICE_NOT_FOUND: Final[str] = "Device not found."
MSG_ROLE_NOT_REGISTERED: Final[str] = "You have no {role} account. Create one first."
MSG_DELETION_REQUEST_NOT_FOUND: Final[str] = "Account deletion request not found."
MSG_DELETION_REQUEST_BLOCKED: Final[str] = (
    "Resolve active bookings, payments, support cases, and legal holds before approval."
)

PATH_TERMS: Final[str] = "/terms"
PATH_TERMS_ACCEPT: Final[str] = "/terms/accept"
TERMS_AUDIENCES: Final[tuple[str, ...]] = ("worker", "business")
MSG_TERMS_REQUIRED: Final[str] = "Please accept the latest Terms & Conditions to continue."
MSG_TERMS_MISSING: Final[str] = "Terms & Conditions are not published yet."
USER_AGENT_MAX_LENGTH: Final[int] = 300
