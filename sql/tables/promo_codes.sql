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

-- Coupon targeting (admin "Promo codes"; columns default so existing codes behave as before):
-- booking_types limits a coupon to Shift or Live Work bookings; min_booking_minor is the minimum
-- work amount (worker pay before fees); is_listed shows a general coupon on the Business
-- Promotions screen (codes assigned to one Business through owner_user_id are always shown to
-- that Business); title is the short text shown there.
ALTER TABLE promo_codes
    ADD COLUMN IF NOT EXISTS booking_types VARCHAR(16) NOT NULL DEFAULT 'all',
    ADD COLUMN IF NOT EXISTS min_booking_minor BIGINT,
    ADD COLUMN IF NOT EXISTS is_listed BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS title VARCHAR(80) NOT NULL DEFAULT '';
ALTER TABLE promo_codes DROP CONSTRAINT IF EXISTS promo_codes_targeting_chk;
ALTER TABLE promo_codes ADD CONSTRAINT promo_codes_targeting_chk CHECK (
    booking_types IN ('all', 'shift', 'live')
    AND (min_booking_minor IS NULL OR min_booking_minor >= 0)
    AND (max_discount_minor IS NULL OR max_discount_minor >= 0)
    AND (valid_until IS NULL OR valid_until > valid_from)
) NOT VALID;
CREATE INDEX IF NOT EXISTS promo_codes_listed_idx
    ON promo_codes (target_role) WHERE is_listed AND is_active AND owner_user_id IS NULL;
