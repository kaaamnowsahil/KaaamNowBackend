"""SQL for shift_invoices, shift_invoice_lines, payments and payment_webhook_events."""

from __future__ import annotations

INSERT_INVOICE = """
INSERT INTO shift_invoices (
    shift_id, business_profile_id, reference, status, currency, worker_subtotal_minor,
    platform_fee_minor, total_minor, fee_percentage, fee_policy_version, issued_at, paid_at,
    invoice_kind, gateway_fee_minor, gateway_fee_percentage, worker_fee_percentage,
    deposit_applied_minor, refund_due_minor, promo_discount_minor, promo_code
)
VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
)
RETURNING id
"""

INSERT_INVOICE_LINE = """
INSERT INTO shift_invoice_lines (
    invoice_id, assignment_id, line_kind, description, minutes, rate_minor, amount_minor,
    sort_order
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""

_INVOICE_SELECT = """
SELECT i.*, s.job_title, s.starts_at AS shift_starts_at
FROM shift_invoices i JOIN shifts s ON s.id = i.shift_id
"""

GET_INVOICE = f"{_INVOICE_SELECT} WHERE i.id = $1"
GET_INVOICE_BY_SHIFT = f"{_INVOICE_SELECT} WHERE i.shift_id = $1 AND i.invoice_kind = $2"
SET_INVOICE_STATUS = "UPDATE shift_invoices SET status = $2, updated_at = now() WHERE id = $1"
SET_REFUND_DUE = """
UPDATE shift_invoices SET refund_due_minor = $2, updated_at = now() WHERE id = $1
"""
LOCK_INVOICE = "SELECT * FROM shift_invoices WHERE id = $1 FOR UPDATE"

LIST_INVOICE_LINES = """
SELECT line_kind, description, assignment_id, minutes, rate_minor, amount_minor
FROM shift_invoice_lines WHERE invoice_id = $1 ORDER BY sort_order
"""

MARK_INVOICE_PAID = """
UPDATE shift_invoices SET status = 'paid', paid_at = $2, updated_at = now() WHERE id = $1
"""

INSERT_PAYMENT = """
INSERT INTO payments (
    invoice_id, business_profile_id, method, provider, amount_minor, currency, reference,
    provider_order_id, upi_payload, checkout_url, expires_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
RETURNING id
"""

_PAYMENT_COLUMNS = """
id, invoice_id, business_profile_id, method, provider, status, amount_minor, currency, reference,
provider_order_id, provider_payment_id, upi_payload, checkout_url, expires_at, paid_at,
failure_reason, created_at
"""

GET_PAYMENT = f"SELECT {_PAYMENT_COLUMNS} FROM payments WHERE id = $1"
LOCK_PAYMENT = f"SELECT {_PAYMENT_COLUMNS} FROM payments WHERE id = $1 FOR UPDATE"
LOCK_PAYMENT_BY_ORDER = f"""
SELECT {_PAYMENT_COLUMNS} FROM payments WHERE provider = $1 AND provider_order_id = $2 FOR UPDATE
"""

CANCEL_PENDING_PAYMENTS = """
UPDATE payments SET status = 'cancelled', updated_at = now()
WHERE invoice_id = $1 AND status = 'pending'
"""

MARK_PAYMENT_SUCCEEDED = """
UPDATE payments SET status = 'succeeded', provider_payment_id = $2, paid_at = $3,
    updated_at = now()
WHERE id = $1
"""

MARK_PAYMENT_FAILED = """
UPDATE payments SET status = $2, failure_reason = $3, updated_at = now() WHERE id = $1
"""

EXPIRE_DUE_PAYMENTS = """
UPDATE payments SET status = 'expired', updated_at = now()
WHERE status = 'pending' AND expires_at <= $1
"""

INSERT_WEBHOOK_EVENT = """
INSERT INTO payment_webhook_events (provider, event_id, event_type, payload)
VALUES ($1, $2, $3, $4)
ON CONFLICT (provider, event_id) DO NOTHING
RETURNING id
"""

MARK_WEBHOOK_PROCESSED = """
UPDATE payment_webhook_events SET processed_at = $2 WHERE id = $1
"""

# $1 business entity ids, $2 statuses, $3 month start, $4 month end, $5 limit, $6 offset
LIST_PAYMENT_HISTORY = """
SELECT i.id AS invoice_id, i.reference AS invoice_reference, i.shift_id, s.job_title,
       s.starts_at AS shift_starts_at, i.status,
       GREATEST(i.total_minor - i.deposit_applied_minor, 0) AS total_minor, i.currency, i.paid_at,
       (SELECT count(*) FROM shift_invoice_lines l
        WHERE l.invoice_id = i.id AND l.line_kind = 'worker_pay') AS worker_count,
       p.id AS payment_id, p.reference AS payment_reference, p.method AS payment_method
FROM shift_invoices i
JOIN shifts s ON s.id = i.shift_id
LEFT JOIN payments p ON p.invoice_id = i.id AND p.status = 'succeeded'
WHERE i.business_profile_id = ANY($1::uuid[])
  AND i.status = ANY($2::varchar[])
  AND ($3::timestamptz IS NULL OR i.issued_at >= $3)
  AND ($4::timestamptz IS NULL OR i.issued_at < $4)
ORDER BY i.issued_at DESC
LIMIT $5 OFFSET $6
"""

PAYMENT_HISTORY_SUMMARY = """
SELECT
    COALESCE(SUM(GREATEST(total_minor - deposit_applied_minor, 0)) FILTER (
        WHERE status = 'paid' AND paid_at >= $2 AND paid_at < $3), 0) AS paid_this_month_minor,
    COALESCE(SUM(GREATEST(total_minor - deposit_applied_minor, 0)) FILTER (
        WHERE status = 'pending'), 0) AS pending_minor
FROM shift_invoices WHERE business_profile_id = ANY($1::uuid[])
"""
