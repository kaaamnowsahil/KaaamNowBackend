-- One row per cancellation / no-show / unfilled-seat release: what each side paid or got.
-- business_retained_minor is kept from the business deposit (fee + commission on it +
-- gateway for that seat); everything else of the deposit is refunded or applied.
CREATE TABLE IF NOT EXISTS cancellation_charges (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id                  UUID NOT NULL,
    assignment_id             UUID,
    party                     VARCHAR(16) NOT NULL,
    event                     VARCHAR(16) NOT NULL,
    policy_version            INTEGER,
    hours_before              NUMERIC(8, 2) NOT NULL,
    seats                     SMALLINT NOT NULL DEFAULT 1,
    booking_minor             BIGINT NOT NULL,
    fee_minor                 BIGINT NOT NULL DEFAULT 0,
    worker_compensation_minor BIGINT NOT NULL DEFAULT 0,
    business_refund_minor     BIGINT NOT NULL DEFAULT 0,
    business_retained_minor   BIGINT NOT NULL DEFAULT 0,
    strike_weight             NUMERIC(3, 1) NOT NULL DEFAULT 0,
    voucher_promo_id          UUID,
    currency                  CHAR(3) NOT NULL,
    created_by_user_id        UUID,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cancellation_charges_party_chk CHECK (party IN ('worker', 'business', 'system')),
    CONSTRAINT cancellation_charges_event_chk
        CHECK (event IN ('cancel', 'no_show', 'walk_off', 'unfilled')),
    CONSTRAINT cancellation_charges_amounts_chk CHECK (
        booking_minor >= 0 AND fee_minor >= 0 AND worker_compensation_minor >= 0
        AND business_refund_minor >= 0 AND business_retained_minor >= 0
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS cancellation_charges_assignment_uid
    ON cancellation_charges (assignment_id) WHERE assignment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cancellation_charges_shift_idx ON cancellation_charges (shift_id);
