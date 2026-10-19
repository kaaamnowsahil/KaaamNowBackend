-- Push tokens for nearby-request / applicant / selection alerts.
CREATE TABLE IF NOT EXISTS user_devices (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    platform     VARCHAR(16) NOT NULL,
    push_token   VARCHAR(512) NOT NULL,
    app_version  VARCHAR(32) NOT NULL DEFAULT '',
    is_active    BOOLEAN NOT NULL DEFAULT true,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_devices_push_token_uid UNIQUE (push_token),
    CONSTRAINT user_devices_platform_chk CHECK (platform IN ('ios', 'android', 'web'))
);

CREATE INDEX IF NOT EXISTS user_devices_user_id_idx ON user_devices (user_id) WHERE is_active;
