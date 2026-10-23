-- Business / Work type chips (many-to-many with business_types). The lowest
-- position mirrors business_profiles.business_type_id (the primary type).
CREATE TABLE IF NOT EXISTS business_profile_types (
    business_profile_id UUID NOT NULL,
    business_type_id    UUID NOT NULL,
    position            SMALLINT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT business_profile_types_pk PRIMARY KEY (business_profile_id, business_type_id)
);

CREATE INDEX IF NOT EXISTS business_profile_types_type_idx
    ON business_profile_types (business_type_id);
