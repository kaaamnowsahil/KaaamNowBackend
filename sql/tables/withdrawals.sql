-- Worker withdrawals (Figma "Withdrawal initiated · WD-20931").
CREATE TABLE IF NOT EXISTS withdrawals (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_profile_id  UUID NOT NULL,
    payout_account_id  UUID NOT NULL,
    amount_minor       BIGINT NOT NULL,
    currency           CHAR(3) NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'initiated',
    reference          VARCHAR(20) NOT NULL,
    idempotency_key    VARCHAR(64) NOT NULL,
    provider           VARCHAR(32) NOT NULL,
    provider_payout_id VARCHAR(128),
    failure_reason     VARCHAR(200),
    initiated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT withdrawals_reference_uid UNIQUE (reference),
    CONSTRAINT withdrawals_idempotency_uid UNIQUE (worker_profile_id, idempotency_key),
    CONSTRAINT withdrawals_status_chk
        CHECK (status IN ('initiated', 'processing', 'paid', 'failed')),
    CONSTRAINT withdrawals_amount_chk CHECK (amount_minor > 0)
);

CREATE INDEX IF NOT EXISTS withdrawals_worker_idx ON withdrawals (worker_profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS withdrawals_in_flight_idx ON withdrawals (status)
    WHERE status IN ('initiated', 'processing');
