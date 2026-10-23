"""SQL for otp_challenges and refresh_tokens."""

from __future__ import annotations

COUNT_OTP_SENDS_SINCE = """
SELECT count(*) AS sends, max(created_at) AS last_sent_at
FROM otp_challenges
WHERE phone = $1 AND created_at >= $2
"""

CONSUME_OPEN_OTP_CHALLENGES = """
UPDATE otp_challenges SET consumed_at = $2
WHERE phone = $1 AND consumed_at IS NULL
"""

INSERT_OTP_CHALLENGE = """
INSERT INTO otp_challenges (phone, purpose, code_hash, expires_at, request_ip)
VALUES ($1, $2, $3, $4, $5)
RETURNING id, expires_at
"""

LOCK_LATEST_OPEN_OTP_CHALLENGE = """
SELECT id, code_hash, expires_at, attempts
FROM otp_challenges
WHERE phone = $1 AND purpose = $2 AND consumed_at IS NULL
ORDER BY created_at DESC
LIMIT 1
FOR UPDATE
"""

RECORD_OTP_ATTEMPT = """
UPDATE otp_challenges
SET attempts = attempts + 1,
    consumed_at = CASE WHEN $2 THEN $3 ELSE consumed_at END
WHERE id = $1
"""

INSERT_REFRESH_TOKEN = """
INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at)
VALUES ($1, $2, $3, $4)
RETURNING id
"""

LOCK_REFRESH_TOKEN_BY_HASH = """
SELECT id, user_id, family_id, expires_at, revoked_at, replaced_by_id
FROM refresh_tokens
WHERE token_hash = $1
FOR UPDATE
"""

MARK_REFRESH_TOKEN_ROTATED = """
UPDATE refresh_tokens SET revoked_at = $2, replaced_by_id = $3 WHERE id = $1
"""

REVOKE_REFRESH_TOKEN_FAMILY = """
UPDATE refresh_tokens SET revoked_at = COALESCE(revoked_at, $2) WHERE family_id = $1
"""

REVOKE_REFRESH_TOKEN_BY_HASH = """
UPDATE refresh_tokens SET revoked_at = COALESCE(revoked_at, $2)
WHERE token_hash = $1 AND user_id = $3
"""

REVOKE_REFRESH_TOKENS_BY_USER = """
UPDATE refresh_tokens SET revoked_at = COALESCE(revoked_at, $2)
WHERE user_id = $1 AND revoked_at IS NULL
"""
