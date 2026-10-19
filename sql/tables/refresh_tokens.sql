-- Rotating refresh tokens. Reusing a rotated token revokes its whole family.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL,
    family_id      UUID NOT NULL,
    token_hash     VARCHAR(128) NOT NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked_at     TIMESTAMPTZ,
    replaced_by_id UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT refresh_tokens_token_hash_uid UNIQUE (token_hash)
);

CREATE INDEX IF NOT EXISTS refresh_tokens_user_id_idx ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS refresh_tokens_family_id_idx ON refresh_tokens (family_id);
