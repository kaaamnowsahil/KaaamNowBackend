"""SQL for self-service account-deletion requests and review."""

from __future__ import annotations

CREATE_REQUEST = """
INSERT INTO account_deletion_requests (user_id)
VALUES ($1)
RETURNING id, user_id, status, requested_at, approved_at, completed_at
"""

GET_OPEN_REQUEST = """
SELECT id, user_id, status, requested_at, approved_at, completed_at
FROM account_deletion_requests
WHERE user_id = $1 AND status IN ('pending', 'approved', 'on_hold')
ORDER BY requested_at DESC
LIMIT 1
"""

GET_LATEST_REQUEST = """
SELECT id, user_id, status, requested_at, approved_at, completed_at
FROM account_deletion_requests
WHERE user_id = $1
ORDER BY requested_at DESC
LIMIT 1
"""

LOCK_REQUEST = """
SELECT id, user_id, status, requested_at, approved_at, completed_at
FROM account_deletion_requests
WHERE id = $1
FOR UPDATE
"""

LIST_REQUESTS = """
SELECT r.id, r.user_id, r.status, r.requested_at, r.approved_at, r.completed_at,
       u.phone, u.full_name,
       COALESCE(
           (SELECT array_agg(ur.role ORDER BY ur.role)
            FROM user_roles ur WHERE ur.user_id = u.id AND ur.status = 'active'),
           ARRAY[]::varchar[]
       ) AS roles
FROM account_deletion_requests r
JOIN users u ON u.id = r.user_id
WHERE ($1::varchar IS NULL OR r.status = $1)
ORDER BY r.requested_at
LIMIT $2 OFFSET $3
"""

COUNT_REQUESTS = """
SELECT count(*) FROM account_deletion_requests
WHERE ($1::varchar IS NULL OR status = $1)
"""

GET_ADMIN_REQUEST = """
SELECT r.id, r.user_id, r.status, r.requested_at, r.approved_at, r.completed_at,
       u.phone, u.full_name,
       COALESCE(
           (SELECT array_agg(ur.role ORDER BY ur.role)
            FROM user_roles ur WHERE ur.user_id = u.id AND ur.status = 'active'),
           ARRAY[]::varchar[]
       ) AS roles
FROM account_deletion_requests r
JOIN users u ON u.id = r.user_id
WHERE r.id = $1
"""

GET_BLOCKER_COUNTS = """
SELECT
    (SELECT count(*)
     FROM shifts s
     JOIN business_profiles bp ON bp.id = s.business_profile_id
     WHERE bp.user_id = $1
       AND s.status IN ('awaiting_payment', 'searching', 'open', 'filled', 'in_progress')
    ) AS active_shifts,
    (SELECT count(*)
     FROM shift_assignments sa
     JOIN worker_profiles wp ON wp.id = sa.worker_profile_id
     WHERE wp.user_id = $1 AND sa.status IN ('confirmed', 'en_route', 'checked_in', 'checked_out')
    ) AS active_bookings,
    (SELECT count(*)
     FROM payments p
     JOIN business_profiles bp ON bp.id = p.business_profile_id
     WHERE bp.user_id = $1 AND p.status = 'pending'
    ) AS pending_payments,
    (SELECT count(*) FROM support_tickets st
     WHERE st.user_id = $1 AND st.status = 'open'
    ) AS open_complaints,
    (SELECT count(*) FROM worker_profiles wp
     WHERE wp.user_id = $1 AND wp.verification_status = 'pending'
    ) +
    (SELECT count(*) FROM business_profiles bp
     WHERE bp.user_id = $1 AND bp.verification_status = 'pending'
    ) AS pending_verification_reviews
"""

LIST_ACTIVE_HOLDS = """
SELECT id, basis, reason, reference, expires_at
FROM account_deletion_holds
WHERE request_id = $1 AND released_at IS NULL AND expires_at > $2
ORDER BY expires_at
"""

LIST_REQUEST_EVENTS = """
SELECT event_type, actor_user_id, details, created_at
FROM account_deletion_events
WHERE request_id = $1
ORDER BY created_at, id
"""

INSERT_EVENT = """
INSERT INTO account_deletion_events (request_id, actor_user_id, event_type, details)
VALUES ($1, $2, $3, $4::jsonb)
"""

ADD_HOLD = """
INSERT INTO account_deletion_holds
    (request_id, basis, reason, reference, expires_at, created_by)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING id, basis, reason, reference, expires_at
"""

SET_REQUEST_ON_HOLD = """
UPDATE account_deletion_requests SET status = 'on_hold', updated_at = now()
WHERE id = $1
"""

RELEASE_HOLD = """
UPDATE account_deletion_holds SET released_at = $3
WHERE id = $1 AND request_id = $2 AND released_at IS NULL
RETURNING id
"""

SET_REQUEST_PENDING_IF_NO_HOLDS = """
UPDATE account_deletion_requests SET status = 'pending', updated_at = now()
WHERE id = $1 AND status = 'on_hold'
  AND NOT EXISTS (
      SELECT 1 FROM account_deletion_holds h
      WHERE h.request_id = $1 AND h.released_at IS NULL AND h.expires_at > $2
  )
"""

APPROVE_REQUEST = """
UPDATE account_deletion_requests
SET status = 'approved', approved_at = $2, updated_at = $2
WHERE id = $1 AND status = 'pending'
RETURNING id
"""

LOCK_APPROVED_REQUESTS = """
SELECT id, user_id
FROM account_deletion_requests
WHERE status = 'approved'
ORDER BY approved_at
LIMIT $1
FOR UPDATE SKIP LOCKED
"""

LOCK_USER = "SELECT id, phone FROM users WHERE id = $1 FOR UPDATE"

ANONYMIZE_USER = """
UPDATE users SET
    phone = '+999' || lpad(nextval('account_deletion_phone_seq')::text, 12, '0'),
    password_hash = NULL,
    full_name = 'Deleted account',
    email = NULL,
    photo_url = NULL,
    is_active = false,
    active_role = NULL,
    language_code = 'en',
    theme_preference = 'dark',
    updated_at = $2
WHERE id = $1
"""

ANONYMIZE_BUSINESS_PROFILE = """
UPDATE business_profiles SET
    business_name = 'Deleted business',
    logo_url = NULL,
    address_text = '',
    locality = '',
    latitude = NULL,
    longitude = NULL,
    verification_note = NULL,
    contact_name = 'Deleted account',
    email = NULL,
    updated_at = $2
WHERE user_id = $1
"""

ANONYMIZE_WORKER_PROFILE = """
UPDATE worker_profiles SET
    address_text = '',
    locality = '',
    latitude = NULL,
    longitude = NULL,
    age = NULL,
    verification_note = NULL,
    is_available = false,
    availability_changed_at = $2,
    updated_at = $2
WHERE user_id = $1
"""

ANONYMIZE_PAYOUT_ACCOUNTS = """
UPDATE payout_accounts pa SET
    account_type = 'upi',
    upi_id = 'deleted-' || replace(pa.id::text, '-', '') || '@invalid',
    paytm_phone = NULL,
    bank_account_number = NULL,
    bank_ifsc = NULL,
    account_holder_name = 'Deleted account',
    is_default = false,
    is_active = false,
    is_verified = false,
    verified_at = NULL,
    updated_at = $2
FROM worker_profiles wp
WHERE pa.worker_profile_id = wp.id AND wp.user_id = $1
"""

ANONYMIZE_ASSIGNMENT_MESSAGES = """
UPDATE assignment_messages SET body = 'Message removed with account'
WHERE sender_user_id = $1;
"""

ANONYMIZE_ATTENDANCE = """
UPDATE attendance_records ar SET
    check_in_latitude = NULL,
    check_in_longitude = NULL,
    check_out_latitude = NULL,
    check_out_longitude = NULL,
    worker_note = '',
    business_note = '',
    updated_at = $2
FROM shift_assignments sa
JOIN worker_profiles wp ON wp.id = sa.worker_profile_id
WHERE ar.assignment_id = sa.id AND wp.user_id = $1;
"""

ANONYMIZE_SHIFTS = """
UPDATE shifts s SET
    workplace_name = '',
    address_text = '',
    latitude = NULL,
    longitude = NULL,
    arrival_instructions = '',
    site_contact_name = '',
    check_in_code = '',
    updated_at = $2
FROM business_profiles bp
WHERE s.business_profile_id = bp.id AND bp.user_id = $1;
"""

ANONYMIZE_RATINGS = """
UPDATE ratings SET review = ''
WHERE rater_user_id = $1 OR ratee_user_id = $1;
"""

ANONYMIZE_CLOSED_SUPPORT_TICKETS = """
UPDATE support_tickets SET subject = 'Account data removed',
    message = 'Personal data removed with account.', updated_at = $2
WHERE user_id = $1 AND status = 'closed';
"""

DELETE_USER_DEVICES = "DELETE FROM user_devices WHERE user_id = $1"
DELETE_USER_NOTIFICATIONS = "DELETE FROM notifications WHERE user_id = $1"
DELETE_USER_OTP_CHALLENGES = "DELETE FROM otp_challenges WHERE phone = $1"
DELETE_USER_REFRESH_TOKENS = "DELETE FROM refresh_tokens WHERE user_id = $1"
DELETE_WORKER_LOCATIONS = """
DELETE FROM worker_locations wl
USING worker_profiles wp
WHERE wl.worker_profile_id = wp.id AND wp.user_id = $1
"""
DELETE_WORKER_CATEGORIES = """
DELETE FROM worker_work_categories wwc
USING worker_profiles wp
WHERE wwc.worker_profile_id = wp.id AND wp.user_id = $1
"""

COMPLETE_REQUEST = """
UPDATE account_deletion_requests
SET status = 'completed', completed_at = $2, updated_at = $2
WHERE id = $1 AND status = 'approved'
RETURNING id
"""

LIST_EXPIRED_HOLDS = """
SELECT id, request_id FROM account_deletion_holds
WHERE released_at IS NULL AND expires_at <= $1
ORDER BY expires_at
LIMIT $2
FOR UPDATE SKIP LOCKED
"""

MARK_HOLD_EXPIRED = """
UPDATE account_deletion_holds SET released_at = expires_at
WHERE id = $1 AND released_at IS NULL
"""
