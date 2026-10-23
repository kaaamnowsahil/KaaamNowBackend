-- One row per phone number. A user may hold both business and worker roles.
CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone            VARCHAR(16) NOT NULL,
    password_hash    TEXT,
    full_name        VARCHAR(120) NOT NULL DEFAULT '',
    email            VARCHAR(254),
    photo_url        TEXT,
    language_code    VARCHAR(8) NOT NULL DEFAULT 'en',
    theme_preference VARCHAR(8) NOT NULL DEFAULT 'dark',
    active_role      VARCHAR(16),
    is_active        BOOLEAN NOT NULL DEFAULT true,
    last_login_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_phone_uid UNIQUE (phone),
    CONSTRAINT users_theme_preference_chk
        CHECK (theme_preference IN ('system', 'light', 'dark')),
    CONSTRAINT users_active_role_chk
        CHECK (active_role IS NULL OR active_role IN ('business', 'worker', 'admin'))
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ALTER COLUMN language_code SET DEFAULT 'en';
ALTER TABLE users ALTER COLUMN theme_preference SET DEFAULT 'dark';
