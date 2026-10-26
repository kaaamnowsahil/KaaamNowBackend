-- One use of a promo code. Business: reserved when the shift is posted, applied on the final
-- invoice, released if the shift is cancelled before it runs. Worker: reserved from the
-- wallet and applied to the commission of the next payout.
CREATE TABLE IF NOT EXISTS promo_redemptions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    promo_code_id  UUID NOT NULL,
    user_id        UUID NOT NULL,
    shift_id       UUID,
    assignment_id  UUID,
    status         VARCHAR(16) NOT NULL DEFAULT 'reserved',
    discount_minor BIGINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at     TIMESTAMPTZ,
    released_at    TIMESTAMPTZ,
    CONSTRAINT promo_redemptions_status_chk
        CHECK (status IN ('reserved', 'applied', 'released')),
    CONSTRAINT promo_redemptions_discount_chk CHECK (discount_minor >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS promo_redemptions_shift_uid
    ON promo_redemptions (shift_id) WHERE shift_id IS NOT NULL AND status <> 'released';
-- A worker holds at most one code waiting for the next payout.
CREATE UNIQUE INDEX IF NOT EXISTS promo_redemptions_worker_pending_uid
    ON promo_redemptions (user_id) WHERE shift_id IS NULL AND status = 'reserved';
CREATE INDEX IF NOT EXISTS promo_redemptions_promo_idx
    ON promo_redemptions (promo_code_id, user_id);
