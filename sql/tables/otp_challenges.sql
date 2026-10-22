-- Phone OTP challenges. Only an HMAC of the code is stored.
CREATE TABLE IF NOT EXISTS otp_challenges (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone       VARCHAR(16) NOT NULL,
    purpose     VARCHAR(24) NOT NULL DEFAULT 'sign_in',
    code_hash   VARCHAR(128) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    attempts    SMALLINT NOT NULL DEFAULT 0,
    consumed_at TIMESTAMPTZ,
    request_ip  VARCHAR(64),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE otp_challenges ADD COLUMN IF NOT EXISTS purpose VARCHAR(24) NOT NULL DEFAULT 'sign_in';

CREATE INDEX IF NOT EXISTS otp_challenges_phone_created_idx
    ON otp_challenges (phone, created_at DESC);
