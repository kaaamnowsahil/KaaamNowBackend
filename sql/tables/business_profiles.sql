-- Figma "Business profile" / "Edit business profile".
CREATE TABLE IF NOT EXISTS business_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    business_name       VARCHAR(160) NOT NULL DEFAULT '',
    category_id         UUID,
    logo_url            TEXT,
    address_text        VARCHAR(500) NOT NULL DEFAULT '',
    locality            VARCHAR(160) NOT NULL DEFAULT '',
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    verification_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    verification_note   VARCHAR(500),
    verified_at         TIMESTAMPTZ,
    verified_by_user_id UUID,
    rating_avg          NUMERIC(3, 2) NOT NULL DEFAULT 0,
    rating_count        INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT business_profiles_user_id_uid UNIQUE (user_id),
    CONSTRAINT business_profiles_verification_chk
        CHECK (verification_status IN ('pending', 'verified', 'rejected'))
);

-- App signup "Contact person", "Email" and "Business type" (Figma business step 2).
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS contact_name VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS email VARCHAR(254);
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS business_type_id UUID;

CREATE INDEX IF NOT EXISTS business_profiles_verification_idx
    ON business_profiles (verification_status);
