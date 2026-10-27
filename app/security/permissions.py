"""Central permission matrix — extend roles here without touching routers.

Resource and action values are defined once below; ``require_access`` call sites
must use these constants so RBAC keys cannot drift. A user may hold several roles
(business + worker); access is granted if any held role allows it.

Ownership (e.g. "this business owns this shift") is enforced in services, not here.
"""

from __future__ import annotations

from typing import Final

from app.constants.application.application_constants import ROLE_ADMIN, ROLE_BUSINESS, ROLE_WORKER

# --- Actions ---
ACTION_READ: Final[str] = "read"
ACTION_WRITE: Final[str] = "write"

# --- Resources ---
RESOURCE_BUSINESS_PROFILE: Final[str] = "business-profile"
RESOURCE_SHIFTS: Final[str] = "shifts"
RESOURCE_BILLING: Final[str] = "billing"
RESOURCE_WORKER_PROFILE: Final[str] = "worker-profile"
RESOURCE_WORK: Final[str] = "work"
RESOURCE_EARNINGS: Final[str] = "earnings"
RESOURCE_VERIFICATION: Final[str] = "verification"
RESOURCE_LIVE_PRICING: Final[str] = "live-pricing"

_READ_WRITE: Final[tuple[str, ...]] = (ACTION_READ, ACTION_WRITE)

_ROLE_PERMISSIONS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    ROLE_BUSINESS: {
        RESOURCE_BUSINESS_PROFILE: _READ_WRITE,
        RESOURCE_SHIFTS: _READ_WRITE,
        RESOURCE_BILLING: _READ_WRITE,
        # Businesses can open a worker's public card from the applicant list.
        RESOURCE_WORKER_PROFILE: (ACTION_READ,),
    },
    ROLE_WORKER: {
        RESOURCE_WORKER_PROFILE: _READ_WRITE,
        RESOURCE_WORK: _READ_WRITE,
        RESOURCE_EARNINGS: _READ_WRITE,
    },
    ROLE_ADMIN: {
        RESOURCE_VERIFICATION: _READ_WRITE,
        RESOURCE_LIVE_PRICING: _READ_WRITE,
        RESOURCE_WORKER_PROFILE: (ACTION_READ,),
        RESOURCE_BUSINESS_PROFILE: (ACTION_READ,),
    },
}


def role_permissions() -> dict[str, dict[str, tuple[str, ...]]]:
    return _ROLE_PERMISSIONS


def role_allows(role: str, resource: str, action: str) -> bool:
    return action in _ROLE_PERMISSIONS.get(role, {}).get(resource, ())


def roles_allow(roles: tuple[str, ...], resource: str, action: str) -> bool:
    return any(role_allows(role, resource, action) for role in roles)
