"""SQL for live_dispatches (live request offers to nearby workers)."""

from __future__ import annotations

# $1/$2 shift lat/lng, $3 radius km, $4 require verified, $5 fresh since, $6/$7 bbox deltas,
# $8 shift id, $9 business user id, $10 category id, $11 shift starts_at, $12 ends_at, $13 limit.
LIST_DISPATCH_CANDIDATES = """
SELECT wp.id AS worker_profile_id, wp.user_id,
       kn_haversine_km($1, $2, wl.latitude, wl.longitude) AS distance_km
FROM worker_profiles wp
JOIN worker_locations wl ON wl.worker_profile_id = wp.id
WHERE wp.is_available
  AND ($4::boolean IS FALSE OR wp.verification_status = 'verified')
  AND wl.recorded_at >= $5
  AND wl.latitude BETWEEN $1 - $6 AND $1 + $6
  AND wl.longitude BETWEEN $2 - $7 AND $2 + $7
  AND kn_haversine_km($1, $2, wl.latitude, wl.longitude) <= $3
  AND wp.user_id <> $9
  AND NOT EXISTS (
      SELECT 1 FROM live_dispatches d WHERE d.shift_id = $8 AND d.worker_profile_id = wp.id
  )
  AND (
      NOT EXISTS (SELECT 1 FROM worker_work_categories c WHERE c.worker_profile_id = wp.id)
      OR EXISTS (SELECT 1 FROM worker_work_categories c
                 WHERE c.worker_profile_id = wp.id AND c.category_id = $10)
  )
  AND NOT EXISTS (
      SELECT 1 FROM shift_assignments sa JOIN shifts s ON s.id = sa.shift_id
      WHERE sa.worker_profile_id = wp.id
        AND sa.status IN ('confirmed', 'en_route', 'checked_in')
        AND s.starts_at < $12 AND s.ends_at > $11
  )
ORDER BY distance_km
LIMIT $13
"""

# Scheduled posting alert: verified workers whose live or home location is within radius.
# $1/$2 shift lat/lng, $3 radius km, $4 require verified, $5/$6 bbox deltas, $7 business user id,
# $8 category id, $9 limit.
LIST_WORKERS_NEAR_SCHEDULED = """
SELECT w.user_id FROM (
    SELECT wp.id, wp.user_id,
           COALESCE(wl.latitude, wp.latitude) AS lat,
           COALESCE(wl.longitude, wp.longitude) AS lng
    FROM worker_profiles wp
    LEFT JOIN worker_locations wl ON wl.worker_profile_id = wp.id
    WHERE ($4::boolean IS FALSE OR wp.verification_status = 'verified')
      AND wp.user_id <> $7
      AND wp.banned_at IS NULL
) w
WHERE w.lat BETWEEN $1::float8 - $5::float8 AND $1::float8 + $5::float8
  AND w.lng BETWEEN $2::float8 - $6::float8 AND $2::float8 + $6::float8
  AND kn_haversine_km($1::float8, $2::float8, w.lat, w.lng) <= $3::float8
  AND (
      NOT EXISTS (SELECT 1 FROM worker_work_categories c WHERE c.worker_profile_id = w.id)
      OR EXISTS (SELECT 1 FROM worker_work_categories c
                 WHERE c.worker_profile_id = w.id AND c.category_id = $8)
  )
LIMIT $9
"""

INSERT_DISPATCHES = """
INSERT INTO live_dispatches (shift_id, worker_profile_id, radius_km, distance_km, expires_at)
SELECT $1, w.worker_profile_id, $2, w.distance_km, $3
FROM unnest($4::uuid[], $5::float8[]) AS w(worker_profile_id, distance_km)
ON CONFLICT (shift_id, worker_profile_id) DO NOTHING
RETURNING worker_profile_id
"""

UPSERT_ACCEPTED_DISPATCH = """
INSERT INTO live_dispatches (
    shift_id, worker_profile_id, radius_km, distance_km, status, expires_at, responded_at
)
VALUES ($1, $2, $3, $4, 'accepted', $5, $5)
ON CONFLICT (shift_id, worker_profile_id) DO UPDATE SET
    status = 'accepted', responded_at = EXCLUDED.responded_at,
    reaccept_count = live_dispatches.reaccept_count + (live_dispatches.status = 'withdrawn')::int,
    updated_at = now()
WHERE live_dispatches.status IN ('offered', 'expired')
   OR (live_dispatches.status = 'withdrawn' AND live_dispatches.reaccept_count < 1)
RETURNING id
"""

GET_DISPATCH = """
SELECT * FROM live_dispatches WHERE shift_id = $1 AND worker_profile_id = $2
"""

LOCK_DISPATCH = """
SELECT * FROM live_dispatches WHERE shift_id = $1 AND worker_profile_id = $2 FOR UPDATE
"""

SET_DISPATCH_STATUS = """
UPDATE live_dispatches SET status = $2, responded_at = $3, updated_at = now() WHERE id = $1
"""

# Worker cancelled before starting: they may accept once more (reaccept_count).
WITHDRAW_ACCEPTED_DISPATCH = """
UPDATE live_dispatches SET status = 'withdrawn', responded_at = $3, updated_at = now()
WHERE shift_id = $1 AND worker_profile_id = $2 AND status = 'accepted'
"""

WITHDRAW_OPEN_OFFERS = """
UPDATE live_dispatches SET status = 'withdrawn', updated_at = now()
WHERE shift_id = $1 AND status = 'offered'
RETURNING worker_profile_id
"""

EXPIRE_DUE_OFFERS = """
UPDATE live_dispatches SET status = 'expired', updated_at = now()
WHERE status = 'offered' AND expires_at <= $1
"""

DELETE_UNANSWERED_DISPATCHES = """
DELETE FROM live_dispatches WHERE shift_id = $1 AND status IN ('expired', 'withdrawn', 'offered')
"""

COUNT_DISPATCHES = "SELECT count(*) FROM live_dispatches WHERE shift_id = $1"

# $1 worker_profile_id, $2 now
LIST_OPEN_OFFERS_FOR_WORKER = """
SELECT d.id AS dispatch_id, d.shift_id, d.expires_at
FROM live_dispatches d
JOIN shifts s ON s.id = d.shift_id
WHERE d.worker_profile_id = $1 AND d.status = 'offered' AND d.expires_at > $2
  AND s.status = 'searching'
ORDER BY d.expires_at
"""
