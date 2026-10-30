"""SQL for shift_assignments, attendance_records and assignment_messages."""

from __future__ import annotations

INSERT_ASSIGNMENT = """
INSERT INTO shift_assignments (
    shift_id, worker_profile_id, source, dispatch_id, application_id, hourly_rate_minor,
    confirmed_at, check_in_code
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
RETURNING id
"""

_CONTEXT_SELECT = """
SELECT a.*, s.business_profile_id, s.status AS shift_status, s.shift_type, s.starts_at,
       s.ends_at, s.break_minutes, s.latitude AS shift_latitude, s.longitude AS shift_longitude,
       s.job_title, s.check_in_code AS shift_check_in_code, s.cancellation_cutoff_hours,
       s.workers_required, s.pricing_mode, s.task_price_minor,
       s.site_contact_name, bp.user_id AS business_user_id, bp.business_name,
       wp.user_id AS worker_user_id,
       ar.id AS attendance_id, ar.checked_in_at, ar.check_in_distance_m, ar.checked_out_at,
       ar.worker_note, ar.recorded_minutes, ar.approved_minutes, ar.business_note,
       ar.approved_at,
       ap.applied_at AS application_applied_at, ap.decided_at AS application_decided_at,
       ap.responded_at AS application_responded_at
FROM shift_assignments a
JOIN shifts s ON s.id = a.shift_id
JOIN business_profiles bp ON bp.id = s.business_profile_id
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
LEFT JOIN attendance_records ar ON ar.assignment_id = a.id
LEFT JOIN shift_applications ap ON ap.id = a.application_id
"""

GET_ASSIGNMENT_CONTEXT = f"{_CONTEXT_SELECT} WHERE a.id = $1"

LOCK_ASSIGNMENT_CONTEXT = f"{_CONTEXT_SELECT} WHERE a.id = $1 FOR UPDATE OF a"

LIST_ROSTER = """
SELECT a.id AS assignment_id, a.status, a.source, a.confirmed_at, a.travel_started_at,
       a.late_cancellation, a.check_in_code, a.extended_minutes, a.ended_reason,
       wp.id AS worker_id, wp.user_id AS worker_user_id, u.full_name, u.photo_url,
       wp.rating_avg, wp.rating_count, wp.completed_shift_count, wp.verification_status,
       ar.id AS attendance_id, ar.checked_in_at, ar.check_in_distance_m, ar.checked_out_at,
       ar.worker_note, ar.recorded_minutes, ar.approved_minutes, ar.business_note,
       ar.approved_at,
       cc.code AS completion_code, cc.failed_attempts AS completion_failed_attempts,
       cc.locked_at AS completion_locked_at, cc.verified_at AS completion_verified_at,
       cc.issued_count AS completion_issued_count
FROM shift_assignments a
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
JOIN users u ON u.id = wp.user_id
LEFT JOIN attendance_records ar ON ar.assignment_id = a.id
LEFT JOIN assignment_completion_codes cc ON cc.assignment_id = a.id
WHERE a.shift_id = $1
ORDER BY (a.status = 'cancelled'), a.confirmed_at
"""

GET_WORKER_SUMMARY = """
SELECT wp.id AS worker_id, wp.user_id AS worker_user_id, u.full_name, u.photo_url, u.phone,
       wp.rating_avg, wp.rating_count, wp.completed_shift_count, wp.verification_status
FROM worker_profiles wp JOIN users u ON u.id = wp.user_id
WHERE wp.id = $1
"""

GET_BUSINESS_CONTACT = """
SELECT bp.business_name, u.full_name, u.phone
FROM business_profiles bp JOIN users u ON u.id = bp.user_id
WHERE bp.id = $1
"""

SET_ASSIGNMENT_STATUS = """
UPDATE shift_assignments SET status = $2, updated_at = now() WHERE id = $1
"""

START_TRAVEL = """
UPDATE shift_assignments SET status = 'en_route', travel_started_at = $2, updated_at = now()
WHERE id = $1
"""

CANCEL_ASSIGNMENT = """
UPDATE shift_assignments SET status = 'cancelled', cancelled_at = $2, cancelled_by_user_id = $3,
    cancel_reason = $4, late_cancellation = $5, updated_at = now()
WHERE id = $1
"""

CANCEL_SHIFT_ASSIGNMENTS = """
UPDATE shift_assignments SET status = 'cancelled', cancelled_at = $2, cancelled_by_user_id = $3,
    cancel_reason = $4, late_cancellation = $5, updated_at = now()
WHERE shift_id = $1 AND status IN ('confirmed', 'en_route')
RETURNING worker_profile_id
"""

LIST_WORKER_USER_IDS_FOR_SHIFT = """
SELECT wp.user_id FROM shift_assignments a JOIN worker_profiles wp ON wp.id = a.worker_profile_id
WHERE a.shift_id = $1 AND a.status = ANY($2::varchar[])
"""

USER_IDS_FOR_WORKER_PROFILES = """
SELECT user_id FROM worker_profiles WHERE id = ANY($1::uuid[])
"""

COUNT_ASSIGNMENTS_IN = """
SELECT count(*) FROM shift_assignments WHERE shift_id = $1 AND status = ANY($2::varchar[])
"""

LIST_SHIFT_ASSIGNMENTS = """
SELECT a.id, a.status, a.worker_profile_id, a.hourly_rate_minor, a.ended_reason,
       wp.user_id AS worker_user_id, u.full_name, ar.recorded_minutes, ar.approved_minutes
FROM shift_assignments a
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
JOIN users u ON u.id = wp.user_id
LEFT JOIN attendance_records ar ON ar.assignment_id = a.id
WHERE a.shift_id = $1
ORDER BY a.confirmed_at
"""

INSERT_MESSAGE = """
INSERT INTO assignment_messages (assignment_id, sender_user_id, body)
VALUES ($1, $2, $3)
RETURNING id, sender_user_id, body, read_at, created_at
"""

LIST_MESSAGES = """
SELECT id, sender_user_id, body, read_at, created_at
FROM assignment_messages
WHERE assignment_id = $1 AND ($2::timestamptz IS NULL OR created_at > $2)
ORDER BY created_at
LIMIT $3
"""

MARK_MESSAGES_READ = """
UPDATE assignment_messages SET read_at = $3
WHERE assignment_id = $1 AND sender_user_id <> $2 AND read_at IS NULL
"""

SET_EARLY_END_PIN = """
UPDATE shift_assignments SET early_end_pin = $2, early_end_requested_by = $3,
    early_end_pin_expires_at = $4, updated_at = now()
WHERE id = $1
"""

SET_ENDED = """
UPDATE shift_assignments SET status = 'checked_out', ended_reason = $2, early_end_pin = NULL,
    early_end_requested_by = NULL, early_end_pin_expires_at = NULL, updated_at = now()
WHERE id = $1
"""

ADD_EXTENDED_MINUTES = """
UPDATE shift_assignments SET extended_minutes = extended_minutes + $2,
    extension_prompted_at = NULL, updated_at = now()
WHERE id = $1
"""

INSERT_EXTENSION = """
INSERT INTO shift_extensions (assignment_id, extra_minutes, requested_by_user_id, requested_at)
VALUES ($1, $2, $3, $4)
RETURNING id
"""

GET_OPEN_EXTENSION = """
SELECT * FROM shift_extensions WHERE assignment_id = $1 AND status = 'requested' FOR UPDATE
"""

GET_EXTENSION = "SELECT * FROM shift_extensions WHERE id = $1 FOR UPDATE"

SET_EXTENSION_STATUS = """
UPDATE shift_extensions SET status = $2, responded_at = $3 WHERE id = $1
"""

LIST_EXTENSIONS = """
SELECT id, extra_minutes, status, requested_at, responded_at
FROM shift_extensions WHERE assignment_id = $1 ORDER BY requested_at DESC
"""

EXPIRE_OPEN_EXTENSIONS = """
UPDATE shift_extensions SET status = 'expired', responded_at = $2
WHERE assignment_id = $1 AND status = 'requested'
"""

LIST_EXTENSION_PROMPTS_DUE = """
SELECT a.id, a.shift_id, s.job_title, bp.user_id AS business_user_id, u.full_name
FROM shift_assignments a
JOIN shifts s ON s.id = a.shift_id
JOIN business_profiles bp ON bp.id = s.business_profile_id
JOIN worker_profiles wp ON wp.id = a.worker_profile_id
JOIN users u ON u.id = wp.user_id
WHERE a.status = 'checked_in' AND a.extension_prompted_at IS NULL
  AND s.pricing_mode = 'hourly'
  AND s.ends_at + make_interval(mins => a.extended_minutes) BETWEEN $1 AND $2
FOR UPDATE OF a SKIP LOCKED
"""

MARK_EXTENSION_PROMPTED = """
UPDATE shift_assignments SET extension_prompted_at = $2 WHERE id = ANY($1::uuid[])
"""
