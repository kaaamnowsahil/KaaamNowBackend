"""SQL for shift_applications."""

from __future__ import annotations

_APPLICATION_COLUMNS = """
ap.id, ap.shift_id, ap.worker_profile_id, ap.status, ap.distance_km, ap.cover_note,
ap.confirm_by, ap.applied_at, ap.decided_at, ap.responded_at
"""

# Re-applying after withdraw / decline / expiry reopens the same row.
UPSERT_APPLICATION = f"""
INSERT INTO shift_applications AS ap (shift_id, worker_profile_id, distance_km, cover_note)
VALUES ($1, $2, $3, $4)
ON CONFLICT (shift_id, worker_profile_id) DO UPDATE SET
    status = 'applied', distance_km = EXCLUDED.distance_km, cover_note = EXCLUDED.cover_note,
    confirm_by = NULL, applied_at = now(), decided_at = NULL, responded_at = NULL,
    updated_at = now()
WHERE ap.status IN ('withdrawn', 'declined', 'expired')
RETURNING {_APPLICATION_COLUMNS}
"""

LOCK_APPLICATION = f"""
SELECT {_APPLICATION_COLUMNS}, s.business_profile_id
FROM shift_applications ap JOIN shifts s ON s.id = ap.shift_id
WHERE ap.id = $1
FOR UPDATE OF ap
"""

GET_APPLICATION = f"""
SELECT {_APPLICATION_COLUMNS},
       (SELECT sa.id FROM shift_assignments sa WHERE sa.application_id = ap.id
        ORDER BY sa.created_at DESC LIMIT 1) AS assignment_id
FROM shift_applications ap WHERE ap.id = $1
"""

SET_APPLICATION_DECISION = """
UPDATE shift_applications SET status = $2, decided_at = $3, confirm_by = $4, updated_at = now()
WHERE id = $1
"""

SET_APPLICATION_RESPONSE = """
UPDATE shift_applications SET status = $2, responded_at = $3, updated_at = now() WHERE id = $1
"""

LIST_APPLICANTS = """
SELECT ap.id AS application_id, ap.status, ap.applied_at, ap.decided_at, ap.responded_at,
       ap.confirm_by, ap.distance_km, ap.cover_note,
       (SELECT sa.id FROM shift_assignments sa WHERE sa.application_id = ap.id
        ORDER BY sa.confirmed_at DESC LIMIT 1) AS assignment_id,
       wp.id AS worker_id, wp.user_id AS worker_user_id, u.full_name, u.photo_url,
       wp.rating_avg, wp.rating_count, wp.completed_shift_count, wp.verification_status
FROM shift_applications ap
JOIN worker_profiles wp ON wp.id = ap.worker_profile_id
JOIN users u ON u.id = wp.user_id
WHERE ap.shift_id = $1 AND ($2::varchar[] IS NULL OR ap.status = ANY($2))
ORDER BY CASE ap.status WHEN 'selected' THEN 0 WHEN 'applied' THEN 1 ELSE 2 END,
         wp.rating_avg DESC, ap.applied_at
"""

LIST_BUSINESS_APPLICANTS = """
SELECT ap.id AS application_id, ap.status, ap.applied_at, ap.decided_at, ap.responded_at,
       ap.confirm_by, ap.distance_km, ap.cover_note,
       (SELECT sa.id FROM shift_assignments sa WHERE sa.application_id = ap.id
        ORDER BY sa.confirmed_at DESC LIMIT 1) AS assignment_id,
       wp.id AS worker_id, wp.user_id AS worker_user_id, u.full_name, u.photo_url,
       wp.rating_avg, wp.rating_count, wp.completed_shift_count, wp.verification_status,
       s.id AS shift_id, s.shift_type, s.status AS shift_status, s.job_title,
       s.workplace_name, s.starts_at, s.ends_at, s.workers_required, s.hourly_rate_minor,
       s.currency
FROM shift_applications ap
JOIN shifts s ON s.id = ap.shift_id
JOIN worker_profiles wp ON wp.id = ap.worker_profile_id
JOIN users u ON u.id = wp.user_id
WHERE s.business_profile_id = ANY($1::uuid[]) AND ap.status = ANY($2::varchar[])
ORDER BY s.starts_at, s.id, wp.rating_avg DESC, ap.applied_at
LIMIT $3 OFFSET $4
"""

CLOSE_OPEN_APPLICATIONS = """
UPDATE shift_applications SET status = $2, decided_at = $3, updated_at = now()
WHERE shift_id = $1 AND status IN ('applied', 'selected')
RETURNING worker_profile_id
"""

REJECT_REMAINING_APPLIED = """
UPDATE shift_applications SET status = 'rejected', decided_at = $2, updated_at = now()
WHERE shift_id = $1 AND status = 'applied'
RETURNING worker_profile_id
"""

COUNT_SELECTED = """
SELECT count(*) FROM shift_applications WHERE shift_id = $1 AND status = 'selected'
"""

EXPIRE_DUE_SELECTIONS = """
UPDATE shift_applications ap SET status = 'expired', responded_at = $1, updated_at = now()
FROM shifts s
WHERE s.id = ap.shift_id AND ap.status = 'selected' AND ap.confirm_by <= $1
RETURNING ap.id, ap.shift_id, ap.worker_profile_id, s.business_profile_id, s.job_title
"""
