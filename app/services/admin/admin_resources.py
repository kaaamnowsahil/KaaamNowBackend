"""Registry of every table the admin dashboard may touch.

Only tables listed here (and present in ``information_schema``) are reachable through
``/api/v1/admin/{resource}``. Columns come from live introspection, so new columns show
up automatically; the registry only declares policy (search, read-only, hidden, ops).
``filterable`` / ``sortable`` default to every visible scalar column when ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from app.constants.admin.admin_route_strings import (
    ALL_WRITE_OPS,
    COLUMN_ID,
    READ_ONLY_OPS,
    READ_UPDATE_OPS,
)


@dataclass(frozen=True, slots=True)
class AdminResource:
    name: str
    table: str
    primary_key: tuple[str, ...] = (COLUMN_ID,)
    operations: frozenset[str] = ALL_WRITE_OPS
    searchable: tuple[str, ...] = ()
    filterable: tuple[str, ...] | None = None
    sortable: tuple[str, ...] | None = None
    read_only: frozenset[str] = field(default_factory=frozenset)
    hidden: frozenset[str] = field(default_factory=frozenset)
    soft_delete: bool = False
    default_sort: str | None = None


def _resource(table: str, **kwargs: object) -> AdminResource:
    return AdminResource(name=table, table=table, **kwargs)  # type: ignore[arg-type]


ADMIN_RESOURCES: Final[tuple[AdminResource, ...]] = (
    # Identity
    _resource(
        "users",
        searchable=("phone", "full_name", "email"),
        read_only=frozenset({"last_login_at"}),
        soft_delete=True,
    ),
    _resource("user_roles", searchable=("role", "status")),
    _resource(
        "user_devices",
        searchable=("platform", "push_token", "app_version"),
        soft_delete=True,
    ),
    _resource(
        "otp_challenges",
        operations=READ_ONLY_OPS,
        searchable=("phone",),
        hidden=frozenset({"code_hash"}),
    ),
    _resource("refresh_tokens", operations=READ_ONLY_OPS, hidden=frozenset({"token_hash"})),
    # Reference catalogs
    _resource(
        "languages",
        primary_key=("code",),
        searchable=("code", "english_name", "native_name"),
        soft_delete=True,
        default_sort="sort_order",
    ),
    _resource(
        "work_categories",
        searchable=("slug", "name"),
        soft_delete=True,
        default_sort="sort_order",
    ),
    _resource("business_types", searchable=("slug", "name"), soft_delete=True),
    _resource("platform_fee_policies", searchable=("notes",), default_sort="-version"),
    # Profiles
    _resource(
        "worker_profiles",
        searchable=("locality", "address_text", "verification_note"),
    ),
    _resource(
        "worker_work_categories",
        primary_key=("worker_profile_id", "category_id"),
    ),
    _resource(
        "worker_locations",
        primary_key=("worker_profile_id",),
        default_sort="-recorded_at",
    ),
    _resource(
        "business_profiles",
        searchable=("business_name", "locality", "address_text", "contact_name", "email"),
    ),
    # Shifts and staffing
    _resource(
        "shifts",
        searchable=("job_title", "workplace_name", "address_text", "check_in_code"),
    ),
    _resource("shift_status_history", operations=READ_ONLY_OPS, searchable=("reason",)),
    _resource("live_dispatches", searchable=("status",)),
    _resource("shift_applications", searchable=("status", "cover_note")),
    _resource("shift_assignments", searchable=("status", "cancel_reason")),
    _resource("attendance_records", searchable=("worker_note", "business_note")),
    _resource("assignment_messages", searchable=("body",)),
    # Billing
    _resource("shift_invoices", searchable=("reference", "status")),
    _resource("shift_invoice_lines", searchable=("description", "line_kind")),
    _resource(
        "payments",
        operations=READ_UPDATE_OPS,
        searchable=("reference", "provider_order_id", "provider_payment_id", "status"),
    ),
    _resource(
        "payment_webhook_events",
        operations=READ_ONLY_OPS,
        searchable=("provider", "event_id", "event_type"),
        default_sort="-received_at",
    ),
    # Earnings
    _resource(
        "payout_accounts",
        searchable=("upi_id", "paytm_phone", "account_holder_name", "bank_ifsc"),
        soft_delete=True,
    ),
    # Creating or deleting a withdrawal outside the earnings service would desync the
    # append-only ledger balance, so the dashboard may only move its status.
    _resource(
        "withdrawals",
        operations=READ_UPDATE_OPS,
        searchable=("reference", "provider_payout_id", "status"),
    ),
    _resource(
        "earning_ledger_entries",
        operations=READ_ONLY_OPS,
        searchable=("description", "entry_type"),
    ),
    # Engagement
    _resource("ratings", searchable=("review", "direction")),
    _resource(
        "notifications",
        searchable=("kind", "title", "body"),
        read_only=frozenset({"pushed_at"}),
    ),
    _resource("content_pages", searchable=("slug", "title", "audience")),
    _resource(
        "faq_entries",
        searchable=("question", "answer", "slug"),
        soft_delete=True,
        default_sort="sort_order",
    ),
    _resource("support_tickets", searchable=("subject", "message", "status", "topic")),
)

_BY_NAME: Final[dict[str, AdminResource]] = {r.name: r for r in ADMIN_RESOURCES}


def find_resource(name: str) -> AdminResource | None:
    return _BY_NAME.get(name)


def registered_tables() -> list[str]:
    return [r.table for r in ADMIN_RESOURCES]
