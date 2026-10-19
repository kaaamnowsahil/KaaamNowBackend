-- Phone OTP challenges. Only an HMAC of the code is stored.
CREATE TABLE IF NOT EXISTS otp_challenges (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone       VARCHAR(16) NOT NULL,
    code_hash   VARCHAR(128) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    attempts    SMALLINT NOT NULL DEFAULT 0,
    consumed_at TIMESTAMPTZ,
    request_ip  VARCHAR(64),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS otp_challenges_phone_created_idx
    ON otp_challenges (phone, created_at DESC);
