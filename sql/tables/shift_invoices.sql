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

CREATE INDEX IF NOT EXISTS shift_invoices_business_idx
    ON shift_invoices (business_profile_id, issued_at DESC);
