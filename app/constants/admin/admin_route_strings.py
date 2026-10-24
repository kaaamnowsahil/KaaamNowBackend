"""Admin dashboard CRUD + metrics route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_ADMIN

ADMIN_CRUD_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_ADMIN}"
OPENAPI_TAG_ADMIN_DATA: Final[str] = "admin - data"

PATH_ADMIN_RESOURCES: Final[str] = "/resources"
PATH_ADMIN_METRICS_OVERVIEW: Final[str] = "/metrics/overview"
PATH_ADMIN_RESOURCE: Final[str] = "/{resource}"
PATH_ADMIN_RESOURCE_EXPORT: Final[str] = "/{resource}/export.csv"
PATH_ADMIN_RECORD: Final[str] = "/{resource}/{record_id}"

# --- Reserved list query params (everything else is treated as a field filter) ---
QUERY_LIMIT: Final[str] = "limit"
QUERY_OFFSET: Final[str] = "offset"
QUERY_SEARCH: Final[str] = "q"
QUERY_SORT: Final[str] = "sort"
RESERVED_LIST_PARAMS: Final[frozenset[str]] = frozenset(
    {QUERY_LIMIT, QUERY_OFFSET, QUERY_SEARCH, QUERY_SORT}
)
SORT_DESC_PREFIX: Final[str] = "-"
FILTER_NULL_LITERAL: Final[str] = "null"
COMPOSITE_KEY_SEPARATOR: Final[str] = ","
SEARCH_MAX_LENGTH: Final[int] = 200

# --- Operations / delete modes (exposed in GET /admin/resources) ---
OP_CREATE: Final[str] = "create"
OP_UPDATE: Final[str] = "update"
OP_DELETE: Final[str] = "delete"
ALL_WRITE_OPS: Final[frozenset[str]] = frozenset({OP_CREATE, OP_UPDATE, OP_DELETE})
READ_UPDATE_OPS: Final[frozenset[str]] = frozenset({OP_UPDATE})
READ_ONLY_OPS: Final[frozenset[str]] = frozenset()
DELETE_MODE_SOFT: Final[str] = "soft"
DELETE_MODE_HARD: Final[str] = "hard"

# --- Column conventions ---
COLUMN_ID: Final[str] = "id"
COLUMN_CREATED_AT: Final[str] = "created_at"
COLUMN_UPDATED_AT: Final[str] = "updated_at"
COLUMN_IS_ACTIVE: Final[str] = "is_active"
GLOBAL_READ_ONLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        COLUMN_ID,
        COLUMN_CREATED_AT,
        COLUMN_UPDATED_AT,
        "rating_avg",
        "rating_count",
        "completed_shift_count",
    }
)
GLOBAL_HIDDEN_COLUMNS: Final[frozenset[str]] = frozenset(
    {"code_hash", "token_hash", "password_hash"}
)
SCHEMA_CACHE_TTL_SECONDS: Final[float] = 60.0
EXPORT_MAX_ROWS: Final[int] = 10_000
EXPORT_MEDIA_TYPE: Final[str] = "text/csv; charset=utf-8"
HEADER_CONTENT_DISPOSITION: Final[str] = "Content-Disposition"
EXPORT_CONTENT_DISPOSITION: Final[str] = 'attachment; filename="{name}.csv"'

# --- Admin-created notifications reuse the inbox payload shape ({"kind": ..., ...}) ---
RESOURCE_NOTIFICATIONS: Final[str] = "notifications"
NOTIFICATION_KIND_COLUMN: Final[str] = "kind"
NOTIFICATION_DATA_COLUMN: Final[str] = "data"

# --- Status values used by the metrics overview ---
SUPPORT_STATUS_OPEN: Final[str] = "open"
WITHDRAWAL_PENDING_STATUSES: Final[tuple[str, ...]] = ("initiated", "processing")
WITHDRAWAL_STATUS_PAID: Final[str] = "paid"
INVOICE_STATUS_PAID: Final[str] = "paid"
PAYMENT_STATUS_SUCCEEDED: Final[str] = "succeeded"

# --- Error codes ---
ERR_RESOURCE_NOT_FOUND: Final[str] = "admin_resource_not_found"
ERR_RECORD_NOT_FOUND: Final[str] = "admin_record_not_found"
ERR_OPERATION_NOT_ALLOWED: Final[str] = "admin_operation_not_allowed"
ERR_INVALID_FIELDS: Final[str] = "admin_invalid_fields"
ERR_INVALID_VALUE: Final[str] = "admin_invalid_value"
ERR_INVALID_SORT: Final[str] = "admin_invalid_sort"
ERR_INVALID_FILTER: Final[str] = "admin_invalid_filter"
ERR_INVALID_KEY: Final[str] = "admin_invalid_key"
ERR_EMPTY_BODY: Final[str] = "admin_empty_body"
ERR_UNIQUE_VIOLATION: Final[str] = "admin_unique_violation"
ERR_FOREIGN_KEY_VIOLATION: Final[str] = "admin_foreign_key_violation"
ERR_CHECK_VIOLATION: Final[str] = "admin_check_violation"
ERR_NOT_NULL_VIOLATION: Final[str] = "admin_not_null_violation"
ERR_INVALID_DATA: Final[str] = "admin_invalid_data"

# --- Messages ---
MSG_RESOURCE_NOT_FOUND: Final[str] = "Unknown admin resource."
MSG_RECORD_NOT_FOUND: Final[str] = "Record not found."
MSG_OPERATION_NOT_ALLOWED: Final[str] = "This operation is not allowed on this resource."
MSG_INVALID_FIELDS: Final[str] = "Some fields are unknown or not writable."
MSG_INVALID_VALUE: Final[str] = "Some values have the wrong type."
MSG_INVALID_SORT: Final[str] = "Cannot sort by this field."
MSG_INVALID_FILTER: Final[str] = "Cannot filter by some of these fields."
MSG_INVALID_KEY: Final[str] = "Invalid record identifier."
MSG_EMPTY_BODY: Final[str] = "Send at least one writable field."
MSG_UNIQUE_VIOLATION: Final[str] = "A record with these values already exists."
MSG_FOREIGN_KEY_VIOLATION: Final[str] = (
    "This change references a missing record or is still referenced by other records."
)
MSG_CHECK_VIOLATION: Final[str] = "A value is outside the allowed set or range."
MSG_NOT_NULL_VIOLATION: Final[str] = "A required field is missing."
MSG_INVALID_DATA: Final[str] = "A value could not be stored in this column."
MSG_FIELD_REQUIRED: Final[str] = "This field cannot be null."
MSG_FIELD_TYPE: Final[str] = "Expected a value of type {data_type}."
MSG_FIELD_UNKNOWN: Final[str] = "Unknown field."
MSG_FIELD_READ_ONLY: Final[str] = "Field is read-only."

DESC_LIST_RESOURCE: Final[str] = (
    "Paginated list. Reserved params: limit, offset, q (ILIKE search on searchable columns), "
    "sort (field or -field). Any other query param is an exact-match filter on a filterable "
    "column (use the literal `null` to match NULL). Composite keys in paths are joined with ','."
)
