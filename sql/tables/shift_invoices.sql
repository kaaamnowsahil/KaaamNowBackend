-- Final shift cost (Figma "Final live shift cost"): worker pay + platform fee.
CREATE TABLE IF NOT EXISTS shift_invoices (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id              UUID NOT NULL,
    business_profile_id   UUID NOT NULL,
    reference             VARCHAR(20) NOT NULL,
    status                VARCHAR(16) NOT NULL DEFAULT 'pending',
    currency              CHAR(3) NOT NULL,
    worker_subtotal_minor BIGINT NOT NULL,
    platform_fee_minor    BIGINT NOT NULL,
    total_minor           BIGINT NOT NULL,
    fee_percentage        NUMERIC(5, 2) NOT NULL,
    fee_policy_version    INTEGER NOT NULL,
    issued_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at               TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shift_invoices_shift_uid UNIQUE (shift_id),
    CONSTRAINT shift_invoices_reference_uid UNIQUE (reference),
    CONSTRAINT shift_invoices_status_chk CHECK (status IN ('pending', 'paid', 'void')),
    CONSTRAINT shift_invoices_total_chk
        CHECK (total_minor = worker_subtotal_minor + platform_fee_minor)
);

ALTER TABLE shift_invoices
    ADD COLUMN IF NOT EXISTS gateway_fee_minor BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gateway_fee_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS worker_fee_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0;
-- ``deposit``: paid when a scheduled shift is posted (booked amount). ``final``: after the
-- shift on approved minutes; the paid deposit is applied and any excess is refunded.
ALTER TABLE shift_invoices
    ADD COLUMN IF NOT EXISTS invoice_kind VARCHAR(16) NOT NULL DEFAULT 'final',
    ADD COLUMN IF NOT EXISTS deposit_applied_minor BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS refund_due_minor BIGINT NOT NULL DEFAULT 0;
-- Live Work: tax is its own amount (never folded into commission); ``live_extension`` invoices
-- bill approved extra time and may repeat per shift. Shift invoices keep tax_minor = 0.
ALTER TABLE shift_invoices
    ADD COLUMN IF NOT EXISTS tax_minor BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax_label VARCHAR(40),
    ADD COLUMN IF NOT EXISTS tax_base VARCHAR(16),
    ADD COLUMN IF NOT EXISTS live_pricing_version INTEGER;
ALTER TABLE shift_invoices DROP CONSTRAINT IF EXISTS shift_invoices_kind_chk;
ALTER TABLE shift_invoices ADD CONSTRAINT shift_invoices_kind_chk
    CHECK (invoice_kind IN ('deposit', 'final', 'live_extension'));
ALTER TABLE shift_invoices DROP CONSTRAINT IF EXISTS shift_invoices_shift_uid;
DROP INDEX IF EXISTS shift_invoices_shift_kind_uid;
CREATE UNIQUE INDEX IF NOT EXISTS shift_invoices_shift_kind_once_uid
    ON shift_invoices (shift_id, invoice_kind) WHERE invoice_kind IN ('deposit', 'final');
ALTER TABLE shift_invoices DROP CONSTRAINT IF EXISTS shift_invoices_total_chk;
ALTER TABLE shift_invoices ADD CONSTRAINT shift_invoices_total_chk CHECK (
    total_minor = worker_subtotal_minor + platform_fee_minor + gateway_fee_minor + tax_minor
);

CREATE INDEX IF NOT EXISTS shift_invoices_business_idx
    ON shift_invoices (business_profile_id, issued_at DESC);

-- Promo discount already taken off commission / gateway (shown as a separate line in apps).
ALTER TABLE shift_invoices
    ADD COLUMN IF NOT EXISTS promo_discount_minor BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS promo_code VARCHAR(32);
