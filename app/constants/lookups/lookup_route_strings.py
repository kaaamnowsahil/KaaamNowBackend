"""Slug-based lookup tables (work categories, business types): one CRUD group each."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.constants.application.application_common import API_V1


@dataclass(frozen=True)
class LookupResource:
    """One lookup table exposed as a CRUD group. ``table`` must be a trusted constant."""

    table: str
    path: str
    tag: str
    label: str
    error_prefix: str


WORK_CATEGORIES: Final[LookupResource] = LookupResource(
    table="work_categories",
    path=f"{API_V1}/work-categories",
    tag="work categories",
    label="work category",
    error_prefix="work_category",
)
BUSINESS_TYPES: Final[LookupResource] = LookupResource(
    table="business_types",
    path=f"{API_V1}/business-types",
    tag="business types",
    label="business type",
    error_prefix="business_type",
)
LOOKUP_RESOURCES: Final[tuple[LookupResource, ...]] = (WORK_CATEGORIES, BUSINESS_TYPES)

PATH_ITEM_SUFFIX: Final[str] = "/{item_id}"

SLUG_PATTERN: Final[str] = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SLUG_MAX_LENGTH: Final[int] = 64
NAME_MAX_LENGTH: Final[int] = 120
ICON_MAX_LENGTH: Final[int] = 64
SEARCH_MAX_LENGTH: Final[int] = 120

ERR_SUFFIX_NOT_FOUND: Final[str] = "_not_found"
ERR_SUFFIX_SLUG_TAKEN: Final[str] = "_slug_taken"
ERR_LOOKUP_EMPTY_UPDATE: Final[str] = "lookup_empty_update"

MSG_LOOKUP_NOT_FOUND: Final[str] = "This {label} was not found."
MSG_LOOKUP_SLUG_TAKEN: Final[str] = "A {label} with this slug already exists."
MSG_LOOKUP_EMPTY_UPDATE: Final[str] = "Send at least one field to update."

SUMMARY_LIST: Final[str] = "List {label}s"
SUMMARY_CREATE: Final[str] = "Create {label}"
SUMMARY_GET: Final[str] = "Get {label}"
SUMMARY_UPDATE: Final[str] = "Update {label}"
SUMMARY_DELETE: Final[str] = "Delete {label}"
DESC_LIST: Final[str] = (
    "Public: active items only, for sign-up and pickers. "
    "include_inactive=true requires an admin token."
)
DESC_GET: Final[str] = "Public for active items; inactive items are visible to admins only."
DESC_DELETE: Final[str] = (
    "Soft delete: sets is_active=false so it disappears from sign-up and pickers. "
    "Existing links are kept. PATCH is_active=true to restore."
)
