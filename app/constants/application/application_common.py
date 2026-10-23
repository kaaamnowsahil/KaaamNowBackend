"""Shared HTTP path segments, path params, and Swagger helpers."""

from __future__ import annotations

from typing import Final

API_V1: Final[str] = "/api/v1"

# --- Path segments ---
SEGMENT_AUTH: Final[str] = "/auth"
SEGMENT_ME: Final[str] = "/me"
SEGMENT_CATALOG: Final[str] = "/catalog"
SEGMENT_BUSINESS: Final[str] = "/business"
SEGMENT_WORKER: Final[str] = "/worker"
SEGMENT_ASSIGNMENTS: Final[str] = "/assignments"
SEGMENT_PAYMENTS: Final[str] = "/payments"
SEGMENT_NOTIFICATIONS: Final[str] = "/notifications"
SEGMENT_CONTENT: Final[str] = "/content"
SEGMENT_SUPPORT: Final[str] = "/support"
SEGMENT_ADMIN: Final[str] = "/admin"

PATH_ROOT: Final[str] = "/"
PATH_HEALTH: Final[str] = "/health"
PATH_MEDIA: Final[str] = "/media"
PATH_FAVICON_ICO: Final[str] = "/favicon.ico"
PATH_FAVICON_SVG: Final[str] = "/favicon.svg"
PATH_APPLE_TOUCH_ICON: Final[str] = "/apple-touch-icon.png"

# --- Static brand assets (files in ``app/static``) ---
FAVICON_SVG_FILE: Final[str] = "favicon.svg"
APPLE_TOUCH_ICON_FILE: Final[str] = "apple-touch-icon.png"
MEDIA_TYPE_SVG: Final[str] = "image/svg+xml"
MEDIA_TYPE_PNG: Final[str] = "image/png"
BRAND_ASSET_CACHE_CONTROL: Final[str] = "public, max-age=86400"

# --- OpenAPI tags ---
OPENAPI_TAG_HEALTH: Final[str] = "health"

# --- Swagger summary role suffixes ---
SWAGGER_ROLE_PUBLIC: Final[str] = "Public"
SWAGGER_ROLE_ANY_USER: Final[str] = "Any signed-in user"
SWAGGER_ROLE_BUSINESS: Final[str] = "Business / Work"
SWAGGER_ROLE_WORKER: Final[str] = "Worker"
SWAGGER_ROLE_PARTICIPANT: Final[str] = "Shift participant"
SWAGGER_ROLE_ADMIN: Final[str] = "Admin"

DESC_ENTITY_FILTER: Final[str] = (
    "Only this Business / Work entity (must be yours). Omit for all of your entities."
)


def swagger_summary(title: str, *roles: str) -> str:
    """``"List Shifts · Business"`` style summaries so Swagger shows who may call."""
    if not roles:
        return title
    return f"{title} · {' / '.join(roles)}"
