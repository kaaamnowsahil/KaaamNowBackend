"""SQL for users, user_roles and user_devices."""

from __future__ import annotations

_USER_COLUMNS = """
u.id, u.phone, u.full_name, u.email, u.photo_url, u.language_code, u.theme_preference,
u.active_role, u.is_active, u.created_at, u.updated_at
"""

UPSERT_USER_BY_PHONE = f"""
WITH inserted AS (
    INSERT INTO users (phone) VALUES ($1)
    ON CONFLICT (phone) DO NOTHING
    RETURNING *, true AS created
)
SELECT {_USER_COLUMNS.replace("u.", "")}, created FROM inserted
UNION ALL
SELECT {_USER_COLUMNS}, false AS created FROM users u
WHERE u.phone = $1 AND NOT EXISTS (SELECT 1 FROM inserted)
"""

GET_PHONE_STATUS = """
SELECT u.id, u.is_active,
       COALESCE(
           (SELECT array_agg(r.role ORDER BY r.role) FROM user_roles r
            WHERE r.user_id = u.id AND r.status = 'active'),
           ARRAY[]::varchar[]
       ) AS roles
FROM users u
WHERE u.phone = $1
"""

GET_AUTH_CREDENTIALS = """
SELECT u.id, u.phone, u.password_hash, u.is_active,
       COALESCE((SELECT array_agg(r.role ORDER BY r.role) FROM user_roles r
                 WHERE r.user_id = u.id AND r.status = 'active'), ARRAY[]::varchar[]) AS roles
FROM users u WHERE u.phone = $1
"""

SET_PASSWORD_BY_PHONE = """
UPDATE users SET password_hash = $2, updated_at = now()
WHERE phone = $1 AND is_active = true
RETURNING id
"""

SET_PASSWORD_IF_MISSING = """
UPDATE users SET password_hash = COALESCE(password_hash, $2), updated_at = now()
WHERE id = $1
"""

TOUCH_LAST_LOGIN = "UPDATE users SET last_login_at = $2 WHERE id = $1"

GET_USER_BY_ID = f"SELECT {_USER_COLUMNS} FROM users u WHERE u.id = $1"

LOCK_USER_BY_ID = "SELECT id FROM users WHERE id = $1 FOR UPDATE"
IS_USER_ACTIVE = "SELECT is_active FROM users WHERE id = $1"

DEACTIVATE_USER_ACCOUNT = """
UPDATE users SET is_active = false, updated_at = now()
WHERE id = $1 AND is_active = true
RETURNING id
"""

DEACTIVATE_USER_DEVICES = """
UPDATE user_devices SET is_active = false, updated_at = now()
WHERE user_id = $1 AND is_active = true
"""

LIST_ACTIVE_ROLES = """
SELECT role FROM user_roles WHERE user_id = $1 AND status = 'active' ORDER BY role
"""

GET_ME = f"""
SELECT {_USER_COLUMNS},
       COALESCE(
           (SELECT array_agg(r.role ORDER BY r.role) FROM user_roles r
            WHERE r.user_id = u.id AND r.status = 'active'),
           ARRAY[]::varchar[]
       ) AS roles,
       bp.id AS business_profile_id, bp.business_name,
       bp.verification_status AS business_verification,
       wp.id AS worker_profile_id, wp.verification_status AS worker_verification, wp.is_available
FROM users u
LEFT JOIN business_profiles bp ON bp.user_id = u.id
LEFT JOIN worker_profiles wp ON wp.user_id = u.id
WHERE u.id = $1
"""

UPDATE_USER_FIELDS = """
UPDATE users SET
    full_name = COALESCE($2, full_name),
    email = CASE WHEN $3::boolean THEN $4 ELSE email END,
    language_code = COALESCE($5, language_code),
    theme_preference = COALESCE($6, theme_preference),
    updated_at = now()
WHERE id = $1
"""

SET_ACTIVE_ROLE = "UPDATE users SET active_role = $2, updated_at = now() WHERE id = $1"

REPLACE_PHOTO_URL = """
UPDATE users u SET photo_url = $2, updated_at = now()
FROM (SELECT id, photo_url FROM users WHERE id = $1 FOR UPDATE) previous
WHERE u.id = previous.id
RETURNING previous.photo_url
"""

GET_PROFILE_IMAGE_URLS = """
SELECT u.photo_url, bp.logo_url
FROM users u LEFT JOIN business_profiles bp ON bp.user_id = u.id
WHERE u.id = $1
"""

UPSERT_USER_ROLE = """
INSERT INTO user_roles (user_id, role) VALUES ($1, $2)
ON CONFLICT (user_id, role) DO NOTHING
"""

LANGUAGE_IS_ACTIVE = "SELECT EXISTS (SELECT 1 FROM languages WHERE code = $1 AND is_active)"

UPSERT_DEVICE = """
INSERT INTO user_devices (user_id, platform, push_token, app_version)
VALUES ($1, $2, $3, $4)
ON CONFLICT (push_token) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    platform = EXCLUDED.platform,
    app_version = EXCLUDED.app_version,
    is_active = true,
    last_seen_at = now(),
    updated_at = now()
RETURNING id, platform, app_version, is_active, last_seen_at
"""

DEACTIVATE_DEVICE = """
UPDATE user_devices SET is_active = false, updated_at = now()
WHERE id = $1 AND user_id = $2
"""

LIST_ACTIVE_PUSH_TOKENS = """
SELECT platform, push_token FROM user_devices WHERE user_id = $1 AND is_active
"""
