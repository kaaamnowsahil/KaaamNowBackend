-- Figma worker "Profile" / "Edit profile". Home location drives scheduled-shift alerts.
CREATE TABLE IF NOT EXISTS worker_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    address_text            VARCHAR(500) NOT NULL DEFAULT '',
    locality                VARCHAR(160) NOT NULL DEFAULT '',
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,
    verification_status     VARCHAR(16) NOT NULL DEFAULT 'pending',
    verification_note       VARCHAR(500),
    verified_at             TIMESTAMPTZ,
    verified_by_user_id     UUID,
    is_available            BOOLEAN NOT NULL DEFAULT false,
    availability_changed_at TIMESTAMPTZ,
    rating_avg              NUMERIC(3, 2) NOT NULL DEFAULT 0,
    rating_count            INTEGER NOT NULL DEFAULT 0,
    completed_shift_count   INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT worker_profiles_user_id_uid UNIQUE (user_id),
    CONSTRAINT worker_profiles_verification_chk
        CHECK (verification_status IN ('pending', 'verified', 'rejected'))
);

CREATE INDEX IF NOT EXISTS worker_profiles_home_geo_idx
    ON worker_profiles (latitude, longitude) WHERE verification_status = 'verified';
