-- Promo codes for workers or businesses. System vouchers (free fees on the next shift) are
-- single-use codes owned by one business user.
CREATE TABLE IF NOT EXISTS promo_codes (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code               VARCHAR(32) NOT NULL,
    target_role        VARCHAR(16) NOT NULL,
    discount_type      VARCHAR(16) NOT NULL,
    discount_value     NUMERIC(10, 2) NOT NULL DEFAULT 0,
    applies_to         VARCHAR(16) NOT NULL,
    max_discount_minor BIGINT,
    valid_from         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until        TIMESTAMPTZ,
    max_uses           INTEGER,
    max_uses_per_user  INTEGER NOT NULL DEFAULT 1,
    used_count         INTEGER NOT NULL DEFAULT 0,
    owner_user_id      UUID,
    source             VARCHAR(16) NOT NULL DEFAULT 'admin',
    source_shift_id    UUID,
    is_active          BOOLEAN NOT NULL DEFAULT true,
    created_by_user_id UUID,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT promo_codes_code_uid UNIQUE (code),
    CONSTRAINT promo_codes_target_role_chk CHECK (target_role IN ('worker', 'business')),
    CONSTRAINT promo_codes_discount_type_chk
        CHECK (discount_type IN ('flat', 'percent', 'waive_fees')),
    CONSTRAINT promo_codes_applies_to_chk
        CHECK (applies_to IN ('commission', 'gateway', 'all_fees')),
    CONSTRAINT promo_codes_source_chk CHECK (source IN ('admin', 'system')),
    CONSTRAINT promo_codes_values_chk CHECK (
        discount_value >= 0 AND (discount_type <> 'percent' OR discount_value <= 100)
        AND (max_uses IS NULL OR max_uses > 0) AND max_uses_per_user > 0 AND used_count >= 0
    )
);

CREATE INDEX IF NOT EXISTS promo_codes_owner_idx
    ON promo_codes (owner_user_id) WHERE owner_user_id IS NOT NULL;
