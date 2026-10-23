"""Ordered SQL paths applied at API bootstrap (relative to ``sql/``).

Extensions and helpers first, then tables (no FKs), then relations (idempotent
``kn_add_foreign_key``). The seed is applied separately by ``bootstrap_database``.
"""

from __future__ import annotations

from typing import Final

SCHEMA_SQL_RELATIVE_PATHS: Final[tuple[str, ...]] = (
    "00_extensions.sql",
    "01_functions.sql",
    # Reference catalogs
    "tables/languages.sql",
    "tables/work_categories.sql",
    "tables/business_types.sql",
    "tables/platform_fee_policies.sql",
    # Identity
    "tables/users.sql",
    "tables/user_roles.sql",
    "tables/otp_challenges.sql",
    "tables/refresh_tokens.sql",
    "tables/user_devices.sql",
    "tables/account_deletion_requests.sql",
    "tables/account_deletion_holds.sql",
    "tables/account_deletion_events.sql",
    # Profiles
    "tables/business_profiles.sql",
    "tables/worker_profiles.sql",
    "tables/worker_work_categories.sql",
    "tables/worker_locations.sql",
    # Shifts and staffing
    "tables/shifts.sql",
    "tables/shift_status_history.sql",
    "tables/live_dispatches.sql",
    "tables/shift_applications.sql",
    "tables/shift_assignments.sql",
    "tables/attendance_records.sql",
    "tables/assignment_messages.sql",
    # Billing
    "tables/shift_invoices.sql",
    "tables/shift_invoice_lines.sql",
    "tables/payments.sql",
    "tables/payment_webhook_events.sql",
    # Earnings
    "tables/payout_accounts.sql",
    "tables/withdrawals.sql",
    "tables/earning_ledger_entries.sql",
    # Engagement
    "tables/ratings.sql",
    "tables/notifications.sql",
    "tables/content_pages.sql",
    "tables/faq_entries.sql",
    "tables/support_tickets.sql",
    # Foreign keys (parent__child naming)
    "relations/languages__users.sql",
    "relations/users__auth.sql",
    "relations/users__account_deletion.sql",
    "relations/users__business_profiles.sql",
    "relations/users__worker_profiles.sql",
    "relations/business_profiles__shifts.sql",
    "relations/shifts__live_dispatches.sql",
    "relations/shifts__shift_applications.sql",
    "relations/shifts__shift_assignments.sql",
    "relations/shift_assignments__attendance_records.sql",
    "relations/shifts__shift_invoices.sql",
    "relations/worker_profiles__earnings.sql",
    "relations/shift_assignments__ratings.sql",
    "relations/users__notifications_support.sql",
)
