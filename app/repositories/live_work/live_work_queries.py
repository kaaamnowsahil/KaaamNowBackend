"""SQL for Live Work: pricing settings + audit, booking snapshots, arrival codes, extensions,
refunds, availability and the admin monitor."""

from __future__ import annotations

SETTINGS_LOCK_KEY = 7_420_101

# --- pricing settings ------------------------------------------------------------------

GET_ACTIVE_SETTINGS = "SELECT * FROM live_pricing_settings WHERE is_active"
NEXT_SETTINGS_VERSION = "SELECT COALESCE(MAX(version), 0) + 1 FROM live_pricing_settings"
DEACTIVATE_SETTINGS = "UPDATE live_pricing_settings SET is_active = false WHERE is_active"
INSERT_SETTINGS = """
INSERT INTO live_pricing_settings (
    version, commission_pct, tax_pct, tax_label, tax_base, extension_surcharge_pct, is_active,
    effective_from, changed_by_user_id, changed_by_label, notes
)
VALUES ($1, $2, $3, $4, $5, $6, true, $7, $8, $9, $10)
RETURNING *
"""
INSERT_AUDIT = """
INSERT INTO live_pricing_audit (
    settings_version, field, old_value, new_value, changed_by_user_id, changed_by_label,
    request_id, changed_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""
LIST_AUDIT = """
SELECT * FROM live_pricing_audit ORDER BY changed_at DESC, field LIMIT $1 OFFSET $2
"""
COUNT_AUDIT = "SELECT count(*) FROM live_pricing_audit"

# --- bookings --------------------------------------------------------------------------

INSERT_BOOKING_PRICING = """
INSERT INTO live_booking_pricing (
    shift_id, business_profile_id, settings_version, currency, hourly_rate_minor,
    reserved_minutes, base_amount_minor, commission_pct, commission_minor, tax_pct, tax_label,
    tax_base, taxable_minor, tax_minor, total_minor, worker_commission_minor, worker_net_minor,
    extension_surcharge_pct, idempotency_key, promo_code_id, promo_code, promo_discount_minor,
    pricing_mode, task_price_minor, workers_required
)
VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
    $21, $22, $23, $24, $25
)
"""
GET_BOOKING_PRICING = "SELECT * FROM live_booking_pricing WHERE shift_id = $1"
FIND_BOOKING_BY_IDEMPOTENCY = """
SELECT shift_id FROM live_booking_pricing WHERE business_profile_id = $1 AND idempotency_key = $2
"""
IS_LIVE_WORK = "SELECT EXISTS (SELECT 1 FROM live_booking_pricing WHERE shift_id = $1)"
GET_SHIFT = "SELECT * FROM shifts WHERE id = $1"

# Posted and priced; waits for the reserved amount to be paid before anyone is notified.
SET_AWAITING_PAYMENT = """
UPDATE shifts SET status = 'awaiting_payment', published_at = $2, fee_policy_version = $3,
    fee_percentage = $4, worker_fee_percentage = $4, gateway_fee_percentage = 0,
    updated_at = now()
WHERE id = $1
"""
START_SEARCH = """
UPDATE shifts SET status = 'searching', starts_at = $2, ends_at = $3, search_radius_km = $4,
    max_search_radius_km = $5, search_started_at = $2, search_expires_at = $6,
    radius_expanded_at = NULL, updated_at = now()
WHERE id = $1
"""

_BOOKING_SELECT = """
SELECT s.id AS shift_id, s.status AS shift_status, s.job_title, s.responsibilities,
       s.address_text, s.latitude, s.longitude, s.arrival_instructions, s.site_contact_name,
       s.workplace_name, s.starts_at, s.ends_at, s.search_started_at, s.search_expires_at,
       s.search_radius_km, s.max_search_radius_km, s.published_at, s.cancelled_at,
       s.cancel_reason, s.created_at, s.updated_at, s.business_profile_id, s.currency,
       s.category_id, wc.slug AS category_slug, wc.name AS category_name,
       bp.business_name, bp.user_id AS business_user_id,
       p.settings_version, p.hourly_rate_minor, p.reserved_minutes, p.base_amount_minor,
       p.commission_pct, p.commission_minor, p.tax_pct, p.tax_label, p.tax_base,
       p.taxable_minor, p.tax_minor, p.total_minor, p.worker_commission_minor,
       p.worker_net_minor, p.extension_surcharge_pct, p.promo_code, p.promo_discount_minor,
       p.pricing_mode, p.task_price_minor, p.workers_required,
       s.workers_required AS open_seats,
       (SELECT count(*) FROM shift_assignments sa
        WHERE sa.shift_id = s.id AND sa.status <> 'cancelled')::int AS workers_filled
FROM live_booking_pricing p
JOIN shifts s ON s.id = p.shift_id
JOIN business_profiles bp ON bp.id = s.business_profile_id
LEFT JOIN work_categories wc ON wc.id = s.category_id
"""
GET_BOOKING = f"{_BOOKING_SELECT} WHERE p.shift_id = $1"
LIST_BUSINESS_BOOKINGS = f"""
{_BOOKING_SELECT}
WHERE s.business_profile_id = ANY($1::uuid[])
  AND ($2::boolean IS FALSE OR s.status IN ('awaiting_payment', 'searching', 'filled',
                                             'in_progress'))
ORDER BY s.created_at DESC
LIMIT $3 OFFSET $4
"""

# Latest seat of the booking (a cancelled one stays visible until a new Worker accepts).
GET_CURRENT_ASSIGNMENT = """
SELECT a.*, wp.user_id AS worker_user_id, u.full_name, u.photo_url, wp.rating_avg,
       wp.rating_count, wp.completed_shift_count, wp.verification_status,
       ar.checked_in_at, ar.checked_out_at, ar.recorded_minutes, ar.approved_minutes
FROM shift_assignments a
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
JOIN users u ON u.id = wp.user_id
LEFT JOIN attendance_records ar ON ar.assignment_id = a.id
WHERE a.shift_id = $1
ORDER BY (a.status = 'cancelled'), a.confirmed_at DESC
LIMIT 1
"""
# Every seat of the booking: active first, then finished, then cancelled.
LIST_ASSIGNMENTS = """
SELECT a.*, wp.user_id AS worker_user_id, u.full_name, u.photo_url, wp.rating_avg,
       wp.rating_count, wp.completed_shift_count, wp.verification_status,
       ar.checked_in_at, ar.checked_out_at, ar.recorded_minutes, ar.approved_minutes
FROM shift_assignments a
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
JOIN users u ON u.id = wp.user_id
LEFT JOIN attendance_records ar ON ar.assignment_id = a.id
WHERE a.shift_id = $1
ORDER BY CASE WHEN a.status IN ('confirmed', 'en_route', 'checked_in') THEN 0
              WHEN a.status = 'cancelled' THEN 2 ELSE 1 END,
         a.confirmed_at
"""
GET_WORKER_ACTIVE_ASSIGNMENT = """
SELECT a.id FROM shift_assignments a
JOIN live_booking_pricing p ON p.shift_id = a.shift_id
WHERE a.worker_profile_id = $1 AND a.status IN ('confirmed', 'en_route', 'checked_in')
ORDER BY a.confirmed_at DESC
LIMIT 1
"""
LIST_WORKER_ASSIGNMENTS = """
SELECT a.id FROM shift_assignments a
JOIN live_booking_pricing p ON p.shift_id = a.shift_id
WHERE a.worker_profile_id = $1
ORDER BY a.confirmed_at DESC
LIMIT $2 OFFSET $3
"""
SET_ASSIGNMENT_STARTED = """
UPDATE shift_assignments SET status = 'checked_in', updated_at = now() WHERE id = $1
"""
SET_ASSIGNMENT_APPROVED = """
UPDATE shift_assignments SET status = 'approved', updated_at = now() WHERE id = $1
"""
SET_SHIFT_WINDOW = (
    "UPDATE shifts SET starts_at = $2, ends_at = $3, updated_at = now() WHERE id = $1"
)
EXTEND_SHIFT_END_TO = """
UPDATE shifts SET ends_at = GREATEST(ends_at, $2), updated_at = now() WHERE id = $1
"""
SET_SHIFT_WORKERS_REQUIRED = """
UPDATE shifts SET workers_required = $2, updated_at = now() WHERE id = $1
"""
EXTEND_SHIFT_END = """
UPDATE shifts SET ends_at = ends_at + make_interval(mins => $2), updated_at = now() WHERE id = $1
"""

LIST_OPEN_OFFERS_FOR_WORKER = """
SELECT d.id AS dispatch_id, d.shift_id, d.expires_at, d.distance_km
FROM live_dispatches d
JOIN live_booking_pricing p ON p.shift_id = d.shift_id
JOIN shifts s ON s.id = d.shift_id
WHERE d.worker_profile_id = $1 AND d.status = 'offered' AND d.expires_at > $2
  AND s.status = 'searching' AND s.search_expires_at > $2
ORDER BY d.created_at DESC
"""
GET_DISPATCH = """
SELECT * FROM live_dispatches WHERE shift_id = $1 AND worker_profile_id = $2
"""

# --- availability ----------------------------------------------------------------------

# Workers who could receive this request now: online, verified (if required), fresh location
# inside the radius, matching category (or no categories), not banned, not already busy.
# $1/$2 lat/lng, $3 radius km, $4 require verified, $5 fresh since, $6/$7 bbox deltas,
# $8 category id (NULL = any), $9 business user id, $10 now.
_AVAILABLE_WORKERS_FROM = """
FROM worker_profiles wp
JOIN worker_locations wl ON wl.worker_profile_id = wp.id
WHERE wp.is_available
  AND wp.banned_at IS NULL
  AND ($4::boolean IS FALSE OR wp.verification_status = 'verified')
  AND wl.recorded_at >= $5
  AND wl.latitude BETWEEN $1::float8 - $6::float8 AND $1::float8 + $6::float8
  AND wl.longitude BETWEEN $2::float8 - $7::float8 AND $2::float8 + $7::float8
  AND kn_haversine_km($1::float8, $2::float8, wl.latitude, wl.longitude) <= $3::float8
  AND wp.user_id <> $9
  AND (
      $8::uuid IS NULL
      OR NOT EXISTS (SELECT 1 FROM worker_work_categories c WHERE c.worker_profile_id = wp.id)
      OR EXISTS (SELECT 1 FROM worker_work_categories c
                 WHERE c.worker_profile_id = wp.id AND c.category_id = $8)
  )
  AND NOT EXISTS (
      SELECT 1 FROM shift_assignments sa JOIN shifts s ON s.id = sa.shift_id
      WHERE sa.worker_profile_id = wp.id
        AND sa.status IN ('confirmed', 'en_route', 'checked_in')
        AND s.starts_at <= $10 AND s.ends_at > $10
  )
"""
COUNT_AVAILABLE_WORKERS = "SELECT count(*)" + _AVAILABLE_WORKERS_FROM
# Map dots for the Business: positions only (no ids), nearest first; $11 limit.
LIST_AVAILABLE_WORKER_POINTS = (
    "SELECT wl.latitude, wl.longitude"
    + _AVAILABLE_WORKERS_FROM
    + "ORDER BY kn_haversine_km($1::float8, $2::float8, wl.latitude, wl.longitude) LIMIT $11"
)

# --- arrival codes ---------------------------------------------------------------------

INSERT_ARRIVAL_CODE = """
INSERT INTO live_arrival_codes (assignment_id, shift_id, code, expires_at)
VALUES ($1, $2, $3, $4)
ON CONFLICT (assignment_id) DO NOTHING
"""
GET_ARRIVAL_CODE = "SELECT * FROM live_arrival_codes WHERE assignment_id = $1"
LOCK_ARRIVAL_CODE = "SELECT * FROM live_arrival_codes WHERE assignment_id = $1 FOR UPDATE"
RECORD_FAILED_ATTEMPT = """
UPDATE live_arrival_codes SET failed_attempts = failed_attempts + 1,
    locked_at = CASE WHEN failed_attempts + 1 >= $2 THEN $3 ELSE locked_at END,
    updated_at = now()
WHERE assignment_id = $1 AND verified_at IS NULL
RETURNING failed_attempts, locked_at
"""
SET_ARRIVAL_VERIFIED = """
UPDATE live_arrival_codes SET verified_at = $2, updated_at = now() WHERE assignment_id = $1
"""
REISSUE_ARRIVAL_CODE = """
UPDATE live_arrival_codes SET code = $2, expires_at = $3, failed_attempts = 0, locked_at = NULL,
    issued_count = issued_count + 1, updated_at = now()
WHERE assignment_id = $1 AND verified_at IS NULL
"""

# --- extensions ------------------------------------------------------------------------

INSERT_EXTENSION = """
INSERT INTO live_extensions (
    shift_id, assignment_id, extra_minutes, hourly_rate_minor, surcharge_pct,
    extension_rate_minor, base_amount_minor, commission_pct, commission_minor, tax_pct,
    tax_base, tax_minor, total_minor, worker_commission_minor, worker_net_minor,
    requested_by_user_id, requested_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
RETURNING id
"""
GET_EXTENSION = "SELECT * FROM live_extensions WHERE id = $1"
LOCK_EXTENSION = "SELECT * FROM live_extensions WHERE id = $1 FOR UPDATE"
LOCK_EXTENSION_BY_INVOICE = "SELECT * FROM live_extensions WHERE invoice_id = $1 FOR UPDATE"
LIST_EXTENSIONS = "SELECT * FROM live_extensions WHERE shift_id = $1 ORDER BY requested_at"
SET_EXTENSION_STATUS = """
UPDATE live_extensions SET status = $2::varchar,
    responded_at = CASE WHEN $2::varchar IN ('awaiting_payment', 'declined') THEN $3
                        ELSE responded_at END,
    applied_at = CASE WHEN $2::varchar = 'applied' THEN $3 ELSE applied_at END,
    cancelled_at = CASE WHEN $2::varchar IN ('cancelled', 'expired') THEN $3 ELSE cancelled_at END,
    updated_at = now()
WHERE id = $1
"""
SET_EXTENSION_INVOICE = """
UPDATE live_extensions SET invoice_id = $2, updated_at = now() WHERE id = $1
"""
LIST_DUE_EXTENSIONS = """
SELECT id FROM live_extensions
WHERE (status = 'requested' AND requested_at < $1)
   OR (status = 'awaiting_payment' AND responded_at < $2)
"""

# --- invoices / payments ---------------------------------------------------------------

INSERT_LIVE_INVOICE = """
INSERT INTO shift_invoices (
    shift_id, business_profile_id, reference, status, currency, worker_subtotal_minor,
    platform_fee_minor, total_minor, fee_percentage, fee_policy_version, issued_at, paid_at,
    invoice_kind, gateway_fee_minor, gateway_fee_percentage, worker_fee_percentage,
    deposit_applied_minor, refund_due_minor, tax_minor, tax_percentage, tax_label, tax_base,
    live_pricing_version, promo_code, promo_discount_minor, assignment_id
)
VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 0, 0, $9, $14, $15, $16, $17, $18,
    $19, $20, $21, $22, $23
)
RETURNING id
"""
LIST_SHIFT_INVOICES = """
SELECT * FROM shift_invoices WHERE shift_id = $1 ORDER BY issued_at, created_at
"""
GET_SUCCEEDED_PAYMENT = """
SELECT * FROM payments WHERE invoice_id = $1 AND status = 'succeeded'
"""
ADD_REFUND_DUE = """
UPDATE shift_invoices SET refund_due_minor = refund_due_minor + $2, updated_at = now()
WHERE id = $1
"""

# --- refunds ---------------------------------------------------------------------------

INSERT_REFUND = """
INSERT INTO live_refunds (
    shift_id, payment_id, invoice_id, amount_minor, currency, reason, idempotency_key,
    provider, created_by_user_id, assignment_id
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING id
"""
LIST_REFUNDS = "SELECT * FROM live_refunds WHERE shift_id = $1 ORDER BY created_at"
REFUND_AMOUNT = "SELECT amount_minor FROM live_refunds WHERE id = $1"
SUM_PAYMENT_REFUNDS = """
SELECT COALESCE(SUM(amount_minor), 0) FROM live_refunds WHERE payment_id = $1
"""
LOCK_DUE_REFUNDS = """
SELECT * FROM live_refunds
WHERE status IN ('pending', 'failed') AND attempts < $1
ORDER BY created_at
LIMIT $2
FOR UPDATE SKIP LOCKED
"""
LOCK_REFUND = "SELECT * FROM live_refunds WHERE id = $1 FOR UPDATE"
SET_REFUND_RESULT = """
UPDATE live_refunds SET status = $2::varchar,
    provider_refund_id = COALESCE($3, provider_refund_id), failure_reason = $4,
    attempts = attempts + 1,
    processed_at = CASE WHEN $2::varchar = 'processed' THEN $5 ELSE processed_at END,
    updated_at = now()
WHERE id = $1
"""
RESET_REFUND_ATTEMPTS = """
UPDATE live_refunds SET attempts = 0, status = 'pending', updated_at = now()
WHERE id = $1 AND status = 'failed'
"""

# --- sweeps ----------------------------------------------------------------------------

LIST_UNPAID_BOOKINGS = """
SELECT s.id FROM live_booking_pricing p JOIN shifts s ON s.id = p.shift_id
WHERE s.status = 'awaiting_payment' AND s.published_at < $1
"""
# Seats whose reserved (+ extended) time ended before $1 and are still working.
LIST_OVERDUE_ACTIVE_SEATS = """
SELECT a.id AS assignment_id, a.shift_id
FROM live_booking_pricing p
JOIN shift_assignments a ON a.shift_id = p.shift_id AND a.status = 'checked_in'
JOIN attendance_records ar ON ar.assignment_id = a.id
WHERE p.pricing_mode = 'hourly'
  AND ar.checked_in_at + make_interval(mins => p.reserved_minutes + a.extended_minutes) < $1
"""

# --- admin -----------------------------------------------------------------------------

_ADMIN_BOOKING_SELECT = f"""
SELECT b.*, a.id AS assignment_id, a.status AS assignment_status, u.full_name AS worker_name,
       (SELECT COALESCE(SUM(r.amount_minor), 0) FROM live_refunds r
        WHERE r.shift_id = b.shift_id AND r.status = 'processed') AS refunded_minor,
       (SELECT count(*) FROM live_refunds r
        WHERE r.shift_id = b.shift_id AND r.status <> 'processed') AS open_refunds
FROM ({_BOOKING_SELECT}) b
LEFT JOIN LATERAL (
    SELECT * FROM shift_assignments sa WHERE sa.shift_id = b.shift_id
    ORDER BY (sa.status = 'cancelled'), sa.confirmed_at DESC LIMIT 1
) a ON true
LEFT JOIN worker_profiles wp ON wp.id = a.worker_profile_id
LEFT JOIN users u ON u.id = wp.user_id
"""
ADMIN_LIST_BOOKINGS = f"""
{_ADMIN_BOOKING_SELECT}
WHERE ($1::text IS NULL OR b.shift_status = $1)
ORDER BY b.created_at DESC
LIMIT $2 OFFSET $3
"""
ADMIN_GET_BOOKING = f"{_ADMIN_BOOKING_SELECT} WHERE b.shift_id = $1"
ADMIN_COUNT_BOOKINGS = """
SELECT count(*) FROM live_booking_pricing p JOIN shifts s ON s.id = p.shift_id
WHERE ($1::text IS NULL OR s.status = $1)
"""
ADMIN_LIST_CANCELLATIONS = """
SELECT c.*, s.job_title FROM cancellation_charges c
JOIN live_booking_pricing p ON p.shift_id = c.shift_id
JOIN shifts s ON s.id = c.shift_id
WHERE c.shift_id = $1
ORDER BY c.created_at
"""
_ADMIN_REFUND_SELECT = """
SELECT r.*, s.job_title FROM live_refunds r JOIN shifts s ON s.id = r.shift_id
"""
ADMIN_LIST_REFUNDS = f"""
{_ADMIN_REFUND_SELECT}
WHERE ($1::text IS NULL OR r.status = $1)
ORDER BY r.created_at DESC
LIMIT $2 OFFSET $3
"""
ADMIN_COUNT_REFUNDS = "SELECT count(*) FROM live_refunds WHERE ($1::text IS NULL OR status = $1)"
ADMIN_LIST_SHIFT_REFUNDS = f"{_ADMIN_REFUND_SELECT} WHERE r.shift_id = $1 ORDER BY r.created_at"
ADMIN_GET_REFUND = f"{_ADMIN_REFUND_SELECT} WHERE r.id = $1"
