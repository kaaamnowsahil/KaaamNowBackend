-- Business payment attempts for an invoice (Figma "Payment · Choose method" / "Scan UPI QR").
CREATE TABLE IF NOT EXISTS payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id          UUID NOT NULL,
    business_profile_id UUID NOT NULL,
    method              VARCHAR(24) NOT NULL,
    provider            VARCHAR(32) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    amount_minor        BIGINT NOT NULL,
    currency            CHAR(3) NOT NULL,
    reference           VARCHAR(20) NOT NULL,
    provider_order_id   VARCHAR(128) NOT NULL,
    provider_payment_id VARCHAR(128),
    upi_payload         TEXT,
    checkout_url        TEXT,
    expires_at          TIMESTAMPTZ NOT NULL,
    paid_at             TIMESTAMPTZ,
    failure_reason      VARCHAR(200),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT payments_reference_uid UNIQUE (reference),
    CONSTRAINT payments_provider_order_uid UNIQUE (provider, provider_order_id),
    CONSTRAINT payments_method_chk CHECK (method IN (
        'google_pay', 'paytm', 'apple_pay', 'upi_qr', 'card_netbanking'
    )),
    CONSTRAINT payments_status_chk
        CHECK (status IN ('pending', 'succeeded', 'failed', 'expired', 'cancelled')),
    CONSTRAINT payments_amount_chk CHECK (amount_minor > 0)
);

-- An invoice can be settled by exactly one successful payment.
CREATE UNIQUE INDEX IF NOT EXISTS payments_one_success_per_invoice_uid
    ON payments (invoice_id) WHERE status = 'succeeded';
CREATE INDEX IF NOT EXISTS payments_business_idx ON payments (business_profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS payments_pending_expiry_idx ON payments (expires_at)
    WHERE status = 'pending';
