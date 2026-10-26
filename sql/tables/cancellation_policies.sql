-- Versioned cancellation / no-show rules (marketplace rules §5, §6, §8). One active version.
CREATE TABLE IF NOT EXISTS cancellation_policies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version             INTEGER NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT false,
    strike_window_days  SMALLINT NOT NULL DEFAULT 90,
    strikes_to_limit    NUMERIC(3, 1) NOT NULL DEFAULT 2,
    limit_days          SMALLINT NOT NULL DEFAULT 7,
    strikes_to_ban      NUMERIC(3, 1) NOT NULL DEFAULT 3,
    voucher_valid_days  SMALLINT NOT NULL DEFAULT 60,
    notes               VARCHAR(200) NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cancellation_policies_version_uid UNIQUE (version)
);

CREATE UNIQUE INDEX IF NOT EXISTS cancellation_policies_one_active_uid
    ON cancellation_policies (is_active) WHERE is_active;

-- A tier applies when hours_from <= hours before start < hours_to (NULL = no upper bound).
-- Fee = flat_fee_minor + booking_pct of the booking amount, capped at fee_cap_minor.
-- worker_share_pct (of the booking amount) goes to the worker when the business cancels.
CREATE TABLE IF NOT EXISTS cancellation_policy_tiers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_version   INTEGER NOT NULL,
    party            VARCHAR(16) NOT NULL,
    event            VARCHAR(16) NOT NULL,
    hours_from       NUMERIC(6, 2) NOT NULL DEFAULT 0,
    hours_to         NUMERIC(6, 2),
    flat_fee_minor   BIGINT NOT NULL DEFAULT 0,
    booking_pct      NUMERIC(5, 2) NOT NULL DEFAULT 0,
    fee_cap_minor    BIGINT,
    worker_share_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    strike_weight    NUMERIC(3, 1) NOT NULL DEFAULT 0,
    business_voucher BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT cancellation_policy_tiers_party_chk CHECK (party IN ('worker', 'business')),
    CONSTRAINT cancellation_policy_tiers_event_chk
        CHECK (event IN ('cancel', 'no_show', 'walk_off')),
    CONSTRAINT cancellation_policy_tiers_window_chk
        CHECK (hours_from >= 0 AND (hours_to IS NULL OR hours_to > hours_from)),
    CONSTRAINT cancellation_policy_tiers_amounts_chk CHECK (
        flat_fee_minor >= 0 AND booking_pct BETWEEN 0 AND 100
        AND worker_share_pct BETWEEN 0 AND booking_pct
        AND (fee_cap_minor IS NULL OR fee_cap_minor >= 0) AND strike_weight >= 0
    ),
    CONSTRAINT cancellation_policy_tiers_uid UNIQUE (policy_version, party, event, hours_from)
);
