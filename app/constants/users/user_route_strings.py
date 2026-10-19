"""Current-user (/me) route + message constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ME

ME_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ME}"
OPENAPI_TAG_ME: Final[str] = "me"

PATH_ACTIVE_ROLE: Final[str] = "/active-role"
PATH_ROLES: Final[str] = "/roles"
PATH_PHOTO: Final[str] = "/photo"
PATH_DEVICES: Final[str] = "/devices"
PATH_DEVICE: Final[str] = "/devices/{device_id}"

THEME_PREFERENCES: Final[tuple[str, ...]] = ("system", "light", "dark")
DEVICE_PLATFORMS: Final[tuple[str, ...]] = ("ios", "android", "web")
ALLOWED_PHOTO_CONTENT_TYPES: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MSG_USER_NOT_FOUND: Final[str] = "User not found."
MSG_ROLE_NOT_HELD: Final[str] = "You do not have this role yet. Add it first."
MSG_ROLE_NOT_SELF_SERVICE: Final[str] = "This role cannot be added from the app."
MSG_LANGUAGE_UNKNOWN: Final[str] = "Unknown or inactive language."
MSG_PHOTO_TYPE: Final[str] = "Photo must be JPEG, PNG or WebP."
MSG_PHOTO_TOO_LARGE: Final[str] = "Photo is larger than the allowed size."
MSG_DEVICE_NOT_FOUND: Final[str] = "Device not found."
