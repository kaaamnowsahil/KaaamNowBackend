"""SQL for shifts, shift_status_history, business dashboard and worker discovery."""

from __future__ import annotations

SEAT_STATUSES_SQL = "('confirmed', 'en_route', 'checked_in', 'checked_out', 'approved')"

_BOOKED_COUNT = f"""
(SELECT count(*) FROM shift_assignments sa
 WHERE sa.shift_id = s.id AND sa.status IN {SEAT_STATUSES_SQL})
"""

# --- Business view -----------------------------------------------------------------

_BUSINESS_SHIFT_SELECT = f"""
SELECT s.*, wc.slug AS category_slug, wc.name AS category_name,
       {_BOOKED_COUNT} AS booked_count,
       (SELECT count(*) FROM shift_assignments sa
        WHERE sa.shift_id = s.id AND sa.status = 'checked_in') AS checked_in_count,
       (SELECT count(*) FROM shift_applications ap
        WHERE ap.shift_id = s.id AND ap.status = 'applied') AS pending_applications,
       i.id AS invoice_id, i.status AS invoice_status
FROM shifts s
JOIN work_categories wc ON wc.id = s.category_id
LEFT JOIN shift_invoices i ON i.shift_id = s.id
"""

INSERT_SHIFT = """
INSERT INTO shifts (
    business_profile_id, category_id, shift_type, job_title, responsibilities, requirements,
    workers_required, hourly_rate_minor, currency, starts_at, ends_at, break_minutes,
    workplace_name, address_text, latitude, longitude, arrival_instructions, site_contact_name,
    check_in_code, cancellation_cutoff_hours
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
RETURNING id
"""

UPDATE_DRAFT_SHIFT = """
UPDATE shifts SET
    category_id = $2, job_title = $3, responsibilities = $4, requirements = $5,
    workers_required = $6, hourly_rate_minor = $7, starts_at = $8, ends_at = $9,
    break_minutes = $10, workplace_name = $11, address_text = $12, latitude = $13,
    longitude = $14, arrival_instructions = $15, site_contact_name = $16,
    cancellation_cutoff_hours = $17, updated_at = now()
WHERE id = $1 AND status = 'draft'
"""

GET_BUSINESS_SHIFT = f"{_BUSINESS_SHIFT_SELECT} WHERE s.id = $1 AND s.business_profile_id = $2"

LOCK_SHIFT = "SELECT * FROM shifts WHERE id = $1 FOR UPDATE"

SET_SHIFT_STATUS = """
UPDATE shifts SET status = $2::varchar, updated_at = now(),
    filled_at = CASE WHEN $2::varchar = 'filled'
        THEN COALESCE(filled_at, $3) ELSE filled_at END,
    started_at = CASE WHEN $2::varchar = 'in_progress'
        THEN COALESCE(started_at, $3) ELSE started_at END,
    completed_at = CASE WHEN $2::varchar = 'completed'
        THEN COALESCE(completed_at, $3) ELSE completed_at END
WHERE id = $1
"""

PUBLISH_LIVE_SHIFT = """
UPDATE shifts SET status = 'searching', published_at = $2, fee_policy_version = $3,
    fee_percentage = $4, search_radius_km = $5, max_search_radius_km = $6,
    search_started_at = $2, search_expires_at = $7, radius_expanded_at = NULL,
    updated_at = now()
WHERE id = $1
"""

PUBLISH_SCHEDULED_SHIFT = """
UPDATE shifts SET status = 'open', shift_type = 'scheduled', published_at = $2,
    fee_policy_version = $3, fee_percentage = $4, search_radius_km = NULL,
    max_search_radius_km = NULL, search_started_at = NULL, search_expires_at = NULL,
    updated_at = now()
WHERE id = $1
"""

CONVERT_TO_SCHEDULED = """
UPDATE shifts SET shift_type = 'scheduled', status = 'open', starts_at = $2, ends_at = $3,
    search_radius_km = NULL, max_search_radius_km = NULL, search_started_at = NULL,
    search_expires_at = NULL, radius_expanded_at = NULL, published_at = $4, updated_at = now()
WHERE id = $1
"""

SET_SHIFT_WINDOW = """
UPDATE shifts SET starts_at = $2, ends_at = $3, updated_at = now() WHERE id = $1
"""

CANCEL_SHIFT = """
UPDATE shifts SET status = 'cancelled', cancelled_at = $2, cancel_reason = $3, updated_at = now()
WHERE id = $1
"""

EXPAND_SEARCH_RADIUS = """
UPDATE shifts SET search_radius_km = max_search_radius_km, radius_expanded_at = $2,
    updated_at = now()
WHERE id = $1
"""

INSERT_STATUS_HISTORY = """
INSERT INTO shift_status_history (shift_id, from_status, to_status, actor_user_id, reason)
VALUES ($1, $2, $3, $4, $5)
"""

COUNT_SEATS = f"""
SELECT count(*) FROM shift_assignments WHERE shift_id = $1 AND status IN {SEAT_STATUSES_SQL}
"""

LIST_BUSINESS_SHIFTS = f"""
{_BUSINESS_SHIFT_SELECT}
WHERE s.business_profile_id = $1
  AND ($2::varchar IS NULL OR s.shift_type = $2)
  AND ($3::varchar[] IS NULL OR s.status = ANY($3))
ORDER BY s.starts_at DESC
LIMIT $4 OFFSET $5
"""

LIST_DASHBOARD_SHIFTS = f"""
{_BUSINESS_SHIFT_SELECT}
WHERE s.business_profile_id = $1 AND s.shift_type = $2
  AND (
      s.status IN ('searching', 'open', 'filled', 'in_progress')
      OR (s.status = 'completed' AND (i.status IS NULL OR i.status = 'pending'))
      OR (s.status = 'expired' AND s.updated_at > $3 - interval '1 day')
  )
ORDER BY s.starts_at
"""

DASHBOARD_SUMMARY = """
SELECT
    (SELECT count(*) FROM shifts s
     WHERE s.business_profile_id = $1
       AND s.status IN ('searching', 'open', 'filled', 'in_progress')) AS active_shifts,
    (SELECT count(*) FROM shift_assignments sa JOIN shifts s ON s.id = sa.shift_id
     WHERE s.business_profile_id = $1
       AND s.status IN ('searching', 'open', 'filled', 'in_progress')
       AND sa.status IN ('confirmed', 'en_route', 'checked_in')) AS workers_booked,
    (SELECT count(*) FROM shift_applications ap JOIN shifts s ON s.id = ap.shift_id
     WHERE s.business_profile_id = $1 AND s.status = 'open'
       AND ap.status = 'applied') AS pending_applications,
    (SELECT count(*) FROM shift_assignments sa JOIN shifts s ON s.id = sa.shift_id
     WHERE s.business_profile_id = $1 AND sa.status = 'checked_out') AS awaiting_review,
    (SELECT count(*) FROM shift_invoices i
     WHERE i.business_profile_id = $1 AND i.status = 'pending') AS unpaid_invoices
"""

COUNT_ACTIVE_WORKERS_NEAR = """
SELECT count(*)
FROM worker_profiles wp
JOIN worker_locations wl ON wl.worker_profile_id = wp.id
WHERE wp.is_available
  AND ($4::boolean IS FALSE OR wp.verification_status = 'verified')
  AND wl.recorded_at >= $5
  AND wl.latitude BETWEEN $1 - $6 AND $1 + $6
  AND wl.longitude BETWEEN $2 - $7 AND $2 + $7
  AND kn_haversine_km($1, $2, wl.latitude, wl.longitude) <= $3
"""

# --- Worker view -------------------------------------------------------------------
# $1 = worker_profile_id, $2/$3 = worker lat/lng (nullable).

WORKER_CARD_SELECT = f"""
SELECT s.id, s.shift_type, s.status, s.job_title, wc.slug AS category_slug,
       wc.name AS category_name, s.workplace_name, s.address_text, s.latitude, s.longitude,
       s.starts_at, s.ends_at, s.break_minutes, s.hourly_rate_minor, s.currency,
       s.workers_required, s.responsibilities, s.requirements, s.arrival_instructions,
       s.site_contact_name, s.cancellation_cutoff_hours, s.business_profile_id,
       s.search_radius_km,
       bp.user_id AS business_user_id, bp.business_name, bp.logo_url,
       bp.rating_avg AS business_rating_avg, bp.rating_count AS business_rating_count,
       bp.verification_status AS business_verification,
       {_BOOKED_COUNT} AS booked_count,
       ap.id AS my_application_id, ap.status AS my_application_status,
       ap.confirm_by AS my_confirm_by, ap.applied_at AS my_applied_at,
       a.id AS my_assignment_id, a.status AS my_assignment_status,
       CASE WHEN $2::float8 IS NULL OR $3::float8 IS NULL THEN NULL
            ELSE kn_haversine_km($2, $3, s.latitude, s.longitude) END AS distance_km
FROM shifts s
JOIN work_categories wc ON wc.id = s.category_id
JOIN business_profiles bp ON bp.id = s.business_profile_id
LEFT JOIN shift_applications ap ON ap.shift_id = s.id AND ap.worker_profile_id = $1
LEFT JOIN LATERAL (
    SELECT x.id, x.status FROM shift_assignments x
    WHERE x.shift_id = s.id AND x.worker_profile_id = $1
    ORDER BY (x.status = 'cancelled'), x.created_at DESC
    LIMIT 1
) a ON true
"""

GET_WORKER_SHIFT = f"{WORKER_CARD_SELECT} WHERE s.id = $4"

# $4 type, $5 category slug, $6 search text, $7..$10 bbox, $11 radius km, $12 own user id,
# $13 now, $14 limit, $15 offset.
FEED_TEMPLATE = f"""
SELECT * FROM (
    {WORKER_CARD_SELECT}
    WHERE s.status IN ('searching', 'open')
      AND bp.user_id <> $12
      AND ($4::varchar IS NULL OR s.shift_type = $4)
      AND ($5::varchar IS NULL OR wc.slug = $5)
      AND ($6::text IS NULL OR s.job_title ILIKE '%' || $6 || '%'
           OR bp.business_name ILIKE '%' || $6 || '%'
           OR s.workplace_name ILIKE '%' || $6 || '%')
      AND s.latitude BETWEEN $7 AND $8
      AND s.longitude BETWEEN $9 AND $10
      AND (
          (s.shift_type = 'scheduled' AND s.starts_at > $13)
          OR (s.shift_type = 'live' AND s.search_expires_at > $13)
      )
) c
WHERE c.distance_km <= $11
  AND (c.booked_count < c.workers_required OR c.my_assignment_id IS NOT NULL)
ORDER BY {{order_by}}
LIMIT $14 OFFSET $15
"""

FEED_ORDER_BY: dict[str, str] = {
    "distance": "c.distance_km, c.starts_at",
    "starts_at": "c.starts_at, c.distance_km",
    "pay": "c.hourly_rate_minor DESC, c.distance_km",
}

# $4 assignment statuses, $5 limit, $6 offset
MY_ASSIGNMENT_SHIFTS = f"""
SELECT c.*,
       (SELECT e.amount_minor FROM earning_ledger_entries e
        WHERE e.assignment_id = c.my_assignment_id AND e.entry_type = 'shift_earning')
           AS earned_minor
FROM ({WORKER_CARD_SELECT} WHERE a.status = ANY($4::varchar[])) c
ORDER BY CASE WHEN $7 THEN c.starts_at END DESC, c.starts_at
LIMIT $5 OFFSET $6
"""

# $4 application statuses, $5 limit, $6 offset
MY_APPLICATION_SHIFTS = f"""
SELECT c.*, NULL::bigint AS earned_minor
FROM ({WORKER_CARD_SELECT} WHERE ap.status = ANY($4::varchar[])) c
ORDER BY c.my_applied_at DESC
LIMIT $5 OFFSET $6
"""

WORKER_HAS_OVERLAP = """
SELECT EXISTS (
    SELECT 1 FROM shift_assignments sa JOIN shifts s ON s.id = sa.shift_id
    WHERE sa.worker_profile_id = $1
      AND sa.status IN ('confirmed', 'en_route', 'checked_in')
      AND s.id <> $4
      AND s.starts_at < $3 AND s.ends_at > $2
)
"""

LIST_DUE_LIVE_EXPANSIONS = """
SELECT id FROM shifts
WHERE shift_type = 'live' AND status = 'searching' AND radius_expanded_at IS NULL
  AND search_radius_km < max_search_radius_km AND search_started_at <= $1
"""

LIST_LIVE_SEARCHES_TO_REFRESH = """
SELECT id FROM shifts
WHERE shift_type = 'live' AND status = 'searching' AND search_expires_at > $1
"""

LIST_TIMED_OUT_LIVE_SEARCHES = """
SELECT id FROM shifts
WHERE shift_type = 'live' AND status = 'searching' AND search_expires_at <= $1
"""

LIST_OPEN_SCHEDULED_PAST_START = """
SELECT id FROM shifts WHERE shift_type = 'scheduled' AND status = 'open' AND starts_at <= $1
"""
