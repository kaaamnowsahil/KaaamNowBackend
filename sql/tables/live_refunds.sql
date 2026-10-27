-- Gateway refunds for Live Work payments. ``status`` follows the provider's server-side answer;
-- ``failed`` rows are retried by the sweep or by an admin. One row per (reason, payment).
CREATE TABLE IF NOT EXISTS live_refunds (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id           UUID NOT NULL,
    payment_id         UUID NOT NULL,
    invoice_id         UUID NOT NULL,
    amount_minor       BIGINT NOT NULL,
    currency           CHAR(3) NOT NULL,
    reason             VARCHAR(40) NOT NULL,
    idempotency_key    VARCHAR(120) NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'pending',
    provider           VARCHAR(32) NOT NULL,
    provider_refund_id VARCHAR(128),
    failure_reason     VARCHAR(200),
    attempts           SMALLINT NOT NULL DEFAULT 0,
    created_by_user_id UUID,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at       TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_refunds_idempotency_uid UNIQUE (idempotency_key),
    CONSTRAINT live_refunds_amount_chk CHECK (amount_minor > 0),
    CONSTRAINT live_refunds_status_chk CHECK (status IN ('pending', 'processed', 'failed'))
);

CREATE INDEX IF NOT EXISTS live_refunds_shift_idx ON live_refunds (shift_id, created_at);
CREATE INDEX IF NOT EXISTS live_refunds_retry_idx ON live_refunds (created_at)
    WHERE status IN ('pending', 'failed');
