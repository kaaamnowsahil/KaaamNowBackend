"""SQL for earning_ledger_entries, payout_accounts and withdrawals."""

from __future__ import annotations

INSERT_SHIFT_EARNINGS_FOR_INVOICE = """
INSERT INTO earning_ledger_entries (
    worker_profile_id, entry_type, amount_minor, currency, assignment_id, invoice_id, description
)
SELECT a.worker_profile_id, 'shift_earning', l.amount_minor, i.currency, a.id, i.id,
       'Shift: ' || s.job_title
FROM shift_invoice_lines l
JOIN shift_invoices i ON i.id = l.invoice_id
JOIN shift_assignments a ON a.id = l.assignment_id
JOIN shifts s ON s.id = i.shift_id
WHERE l.invoice_id = $1 AND l.line_kind = 'worker_pay' AND l.amount_minor > 0
ON CONFLICT DO NOTHING
RETURNING worker_profile_id, amount_minor
"""

INSERT_WORKER_COMMISSIONS_FOR_INVOICE = """
INSERT INTO earning_ledger_entries (
    worker_profile_id, entry_type, amount_minor, currency, assignment_id, invoice_id, description
)
SELECT a.worker_profile_id, 'commission',
       -round(l.amount_minor * i.worker_fee_percentage / 100)::bigint, i.currency, a.id, i.id,
       'Platform charge ' || trim_scale(i.worker_fee_percentage)::text || '%: ' || s.job_title
FROM shift_invoice_lines l
JOIN shift_invoices i ON i.id = l.invoice_id
JOIN shift_assignments a ON a.id = l.assignment_id
JOIN shifts s ON s.id = i.shift_id
WHERE l.invoice_id = $1 AND l.line_kind = 'worker_pay'
  AND round(l.amount_minor * i.worker_fee_percentage / 100) > 0
ON CONFLICT DO NOTHING
RETURNING worker_profile_id, amount_minor, assignment_id, currency
"""

INSERT_LEDGER_ENTRY = """
INSERT INTO earning_ledger_entries (
    worker_profile_id, entry_type, amount_minor, currency, withdrawal_id, description
)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT DO NOTHING
"""

BALANCE = """
SELECT COALESCE(SUM(amount_minor), 0) FROM earning_ledger_entries WHERE worker_profile_id = $1
"""

EARNINGS_SUMMARY = """
SELECT
    COALESCE(SUM(amount_minor), 0) AS available_minor,
    COALESCE(SUM(amount_minor) FILTER (WHERE entry_type IN (
        'shift_earning', 'commission', 'cancellation_compensation', 'promo_credit'
    )), 0) AS lifetime_minor,
    COALESCE(SUM(amount_minor) FILTER (WHERE entry_type IN (
        'shift_earning', 'commission', 'cancellation_compensation', 'promo_credit'
    ) AND created_at >= $2), 0) AS this_month_minor
FROM earning_ledger_entries WHERE worker_profile_id = $1
"""

PENDING_PAY = """
SELECT COALESCE(SUM(l.amount_minor), 0)
FROM shift_invoice_lines l
JOIN shift_invoices i ON i.id = l.invoice_id
JOIN shift_assignments a ON a.id = l.assignment_id
WHERE a.worker_profile_id = $1 AND i.status = 'pending' AND l.line_kind = 'worker_pay'
"""

IN_FLIGHT_WITHDRAWALS = """
SELECT COALESCE(SUM(amount_minor), 0) FROM withdrawals
WHERE worker_profile_id = $1 AND status IN ('initiated', 'processing')
"""

# Workers see what they take home: each job's platform-charge debit and platform share (work
# stopped by the Business) are folded into its earning.
_PLATFORM_DEBIT = """({t}.entry_type = 'commission'
    OR ({t}.entry_type = 'adjustment' AND {t}.description LIKE 'Platform share%'))"""

LIST_LEDGER = f"""
SELECT e.id, e.entry_type, e.amount_minor + COALESCE(fee.total, 0) AS amount_minor,
       e.currency, e.assignment_id, e.withdrawal_id, e.description, e.created_at
FROM earning_ledger_entries e
LEFT JOIN LATERAL (
    SELECT SUM(f.amount_minor) AS total FROM earning_ledger_entries f
    WHERE e.entry_type = 'shift_earning' AND f.assignment_id = e.assignment_id
      AND f.worker_profile_id = e.worker_profile_id AND {_PLATFORM_DEBIT.format(t="f")}
) fee ON true
WHERE e.worker_profile_id = $1
  AND NOT ({_PLATFORM_DEBIT.format(t="e")} AND EXISTS (
      SELECT 1 FROM earning_ledger_entries s
      WHERE s.entry_type = 'shift_earning' AND s.assignment_id = e.assignment_id
  ))
ORDER BY e.created_at DESC
LIMIT $2 OFFSET $3
"""

ASSIGNMENT_NET = f"""
SELECT SUM(amount_minor) FROM earning_ledger_entries e
WHERE e.worker_profile_id = $1 AND e.assignment_id = $2
  AND (e.entry_type = 'shift_earning' OR {_PLATFORM_DEBIT.format(t="e")})
"""

_ACCOUNT_COLUMNS = """
id, account_type, upi_id, paytm_phone, bank_account_number, bank_ifsc, account_holder_name,
is_default, is_verified, verified_at, created_at
"""

LIST_PAYOUT_ACCOUNTS = f"""
SELECT {_ACCOUNT_COLUMNS} FROM payout_accounts
WHERE worker_profile_id = $1 AND is_active
ORDER BY is_default DESC, created_at
"""

GET_PAYOUT_ACCOUNT = f"""
SELECT {_ACCOUNT_COLUMNS} FROM payout_accounts
WHERE id = $1 AND worker_profile_id = $2 AND is_active
"""

CLEAR_DEFAULT_ACCOUNT = """
UPDATE payout_accounts SET is_default = false, updated_at = now()
WHERE worker_profile_id = $1 AND is_default
"""

INSERT_PAYOUT_ACCOUNT = f"""
INSERT INTO payout_accounts (
    worker_profile_id, account_type, upi_id, paytm_phone, bank_account_number, bank_ifsc,
    account_holder_name, is_default
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
RETURNING {_ACCOUNT_COLUMNS}
"""

UPDATE_PAYOUT_ACCOUNT = f"""
UPDATE payout_accounts SET
    upi_id = COALESCE($3, upi_id),
    paytm_phone = COALESCE($4, paytm_phone),
    bank_account_number = COALESCE($5, bank_account_number),
    bank_ifsc = COALESCE($6, bank_ifsc),
    account_holder_name = COALESCE($7, account_holder_name),
    is_verified = CASE WHEN $8::boolean THEN false ELSE is_verified END,
    verified_at = CASE WHEN $8::boolean THEN NULL ELSE verified_at END,
    updated_at = now()
WHERE id = $1 AND worker_profile_id = $2 AND is_active
RETURNING {_ACCOUNT_COLUMNS}
"""

SET_DEFAULT_ACCOUNT = """
UPDATE payout_accounts SET is_default = true, updated_at = now()
WHERE id = $1 AND worker_profile_id = $2 AND is_active
"""

DEACTIVATE_PAYOUT_ACCOUNT = """
UPDATE payout_accounts SET is_active = false, is_default = false, updated_at = now()
WHERE id = $1 AND worker_profile_id = $2 AND is_active
"""

COUNT_ACTIVE_ACCOUNTS = """
SELECT count(*) FROM payout_accounts WHERE worker_profile_id = $1 AND is_active
"""

LOCK_WORKER_LEDGER = "SELECT pg_advisory_xact_lock(hashtext($1::text))"

_WITHDRAWAL_SELECT = """
SELECT w.id, w.worker_profile_id, w.payout_account_id, w.amount_minor, w.currency, w.status,
       w.reference, w.idempotency_key, w.provider, w.provider_payout_id, w.failure_reason,
       w.initiated_at, w.completed_at,
       pa.account_type, pa.upi_id, pa.paytm_phone, pa.bank_account_number, pa.bank_ifsc
FROM withdrawals w JOIN payout_accounts pa ON pa.id = w.payout_account_id
"""

GET_WITHDRAWAL = f"{_WITHDRAWAL_SELECT} WHERE w.id = $1 AND w.worker_profile_id = $2"
GET_WITHDRAWAL_BY_KEY = (
    f"{_WITHDRAWAL_SELECT} WHERE w.worker_profile_id = $1 AND w.idempotency_key = $2"
)
LIST_WITHDRAWALS = f"""
{_WITHDRAWAL_SELECT} WHERE w.worker_profile_id = $1
ORDER BY w.initiated_at DESC LIMIT $2 OFFSET $3
"""

INSERT_WITHDRAWAL = """
INSERT INTO withdrawals (
    worker_profile_id, payout_account_id, amount_minor, currency, reference, idempotency_key,
    provider
)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id
"""

SET_WITHDRAWAL_PROCESSING = """
UPDATE withdrawals SET status = 'processing', provider_payout_id = $2, updated_at = now()
WHERE id = $1
"""

LIST_IN_FLIGHT_WITHDRAWALS = """
SELECT id FROM withdrawals WHERE status IN ('initiated', 'processing') ORDER BY initiated_at
LIMIT $1
"""

LOCK_WITHDRAWAL = """
SELECT w.*, wp.user_id FROM withdrawals w JOIN worker_profiles wp ON wp.id = w.worker_profile_id
WHERE w.id = $1 FOR UPDATE OF w
"""

FINISH_WITHDRAWAL = """
UPDATE withdrawals SET status = $2, failure_reason = $3, completed_at = $4, updated_at = now()
WHERE id = $1
"""
