-- Price snapshot of one Live Work booking (a live shift with one worker), taken when it is
-- posted. Later settings changes never touch it. Amounts in paise.
CREATE TABLE IF NOT EXISTS live_booking_pricing (
    shift_id                UUID PRIMARY KEY,
    business_profile_id     UUID NOT NULL,
    settings_version        INTEGER NOT NULL,
    currency                CHAR(3) NOT NULL,
    hourly_rate_minor       BIGINT NOT NULL,
    reserved_minutes        INTEGER NOT NULL,
    base_amount_minor       BIGINT NOT NULL,
    commission_pct          NUMERIC(5, 2) NOT NULL,
    commission_minor        BIGINT NOT NULL,
    tax_pct                 NUMERIC(5, 2) NOT NULL,
    tax_label               VARCHAR(40) NOT NULL,
    tax_base                VARCHAR(16) NOT NULL,
    taxable_minor           BIGINT NOT NULL,
    tax_minor               BIGINT NOT NULL,
    total_minor             BIGINT NOT NULL,
    worker_commission_minor BIGINT NOT NULL,
    worker_net_minor        BIGINT NOT NULL,
    extension_surcharge_pct NUMERIC(5, 2) NOT NULL,
    idempotency_key         VARCHAR(64),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_booking_pricing_minutes_chk CHECK (reserved_minutes > 0),
    CONSTRAINT live_booking_pricing_amounts_chk CHECK (
        hourly_rate_minor > 0 AND base_amount_minor >= 0 AND commission_minor >= 0
        AND taxable_minor >= 0 AND tax_minor >= 0 AND worker_commission_minor >= 0
    ),
    CONSTRAINT live_booking_pricing_total_chk
        CHECK (total_minor = base_amount_minor + commission_minor + tax_minor),
    CONSTRAINT live_booking_pricing_worker_chk
        CHECK (worker_net_minor = base_amount_minor - worker_commission_minor)
);

-- A retried "Post Work" with the same key returns the booking it already created.
CREATE UNIQUE INDEX IF NOT EXISTS live_booking_pricing_idempotency_uid
    ON live_booking_pricing (business_profile_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Business coupon, snapshotted at posting. The discount only reduces commission; the coupon row
-- may change or be deleted later without touching this booking.
ALTER TABLE live_booking_pricing
    ADD COLUMN IF NOT EXISTS promo_code_id        UUID,
    ADD COLUMN IF NOT EXISTS promo_code           VARCHAR(40),
    ADD COLUMN IF NOT EXISTS promo_discount_minor BIGINT NOT NULL DEFAULT 0;

ALTER TABLE live_booking_pricing DROP CONSTRAINT IF EXISTS live_booking_pricing_total_chk;
ALTER TABLE live_booking_pricing ADD CONSTRAINT live_booking_pricing_total_chk CHECK (
    promo_discount_minor >= 0 AND promo_discount_minor <= commission_minor
    AND total_minor = base_amount_minor + commission_minor - promo_discount_minor + tax_minor
);
