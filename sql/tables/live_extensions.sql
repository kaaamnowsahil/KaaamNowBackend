-- "Extend Work": Business requests extra time → Worker accepts → Business pays the extension
-- invoice → time is added. Priced from the booking snapshot (rate × (100 + surcharge)%).
CREATE TABLE IF NOT EXISTS live_extensions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id                UUID NOT NULL,
    assignment_id           UUID NOT NULL,
    extra_minutes           INTEGER NOT NULL,
    hourly_rate_minor       BIGINT NOT NULL,
    surcharge_pct           NUMERIC(5, 2) NOT NULL,
    extension_rate_minor    BIGINT NOT NULL,
    base_amount_minor       BIGINT NOT NULL,
    commission_pct          NUMERIC(5, 2) NOT NULL,
    commission_minor        BIGINT NOT NULL,
    tax_pct                 NUMERIC(5, 2) NOT NULL,
    tax_base                VARCHAR(16) NOT NULL,
    tax_minor               BIGINT NOT NULL,
    total_minor             BIGINT NOT NULL,
    worker_commission_minor BIGINT NOT NULL,
    worker_net_minor        BIGINT NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'requested',
    invoice_id              UUID,
    requested_by_user_id    UUID,
    requested_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at            TIMESTAMPTZ,
    applied_at              TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_extensions_minutes_chk CHECK (extra_minutes > 0),
    CONSTRAINT live_extensions_status_chk CHECK (status IN (
        'requested', 'awaiting_payment', 'applied', 'declined', 'cancelled', 'expired'
    )),
    CONSTRAINT live_extensions_total_chk
        CHECK (total_minor = base_amount_minor + commission_minor + tax_minor)
);

-- One open extension per booking: no overlapping timers or duplicate charges.
CREATE UNIQUE INDEX IF NOT EXISTS live_extensions_one_open_uid
    ON live_extensions (assignment_id) WHERE status IN ('requested', 'awaiting_payment');
CREATE INDEX IF NOT EXISTS live_extensions_shift_idx ON live_extensions (shift_id, requested_at);
CREATE UNIQUE INDEX IF NOT EXISTS live_extensions_invoice_uid
    ON live_extensions (invoice_id) WHERE invoice_id IS NOT NULL;
