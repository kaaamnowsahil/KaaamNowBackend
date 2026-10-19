"""SQL for attendance_records."""

from __future__ import annotations

INSERT_CHECK_IN = """
INSERT INTO attendance_records (
    assignment_id, checked_in_at, check_in_latitude, check_in_longitude, check_in_distance_m
)
VALUES ($1, $2, $3, $4, $5)
"""

SET_CHECK_OUT = """
UPDATE attendance_records SET checked_out_at = $2, check_out_latitude = $3,
    check_out_longitude = $4, worker_note = $5, recorded_minutes = $6, updated_at = now()
WHERE assignment_id = $1
"""

APPROVE = """
UPDATE attendance_records SET approved_minutes = $2, business_note = $3, approved_at = $4,
    approved_by_user_id = $5, updated_at = now()
WHERE assignment_id = $1
"""

AUTO_APPROVE_CHECKED_OUT = """
WITH approved AS (
    UPDATE attendance_records ar SET approved_minutes = ar.recorded_minutes, approved_at = $2,
        approved_by_user_id = $3, business_note = 'Auto-approved at invoicing',
        updated_at = now()
    FROM shift_assignments a
    WHERE a.id = ar.assignment_id AND a.shift_id = $1 AND a.status = 'checked_out'
    RETURNING a.id
)
UPDATE shift_assignments SET status = 'approved', updated_at = now()
WHERE id IN (SELECT id FROM approved)
"""
