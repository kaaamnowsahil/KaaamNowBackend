-- Versioned platform fee (Figma: 5% on top of worker pay). Snapshotted onto shifts at publish.
CREATE TABLE IF NOT EXISTS platform_fee_policies (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version    INTEGER NOT NULL,
    percentage NUMERIC(5, 2) NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT false,
    notes      VARCHAR(200) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT platform_fee_policies_version_uid UNIQUE (version),
    CONSTRAINT platform_fee_policies_percentage_chk CHECK (percentage >= 0 AND percentage <= 100)
);

-- ``percentage`` is the business commission. Worker commission is deducted from worker pay;
-- the gateway charge is added for the business on top of pay + commission.
ALTER TABLE platform_fee_policies
    ADD COLUMN IF NOT EXISTS worker_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gateway_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS platform_fee_policies_one_active_uid
    ON platform_fee_policies (is_active) WHERE is_active;

-- Tax on Shift bookings (shared pricing with Live Work). Defaults let a version created without
-- tax fields carry the standard 2% on worker pay + business commission. Not GST: the label is
-- configurable and the rate is whatever the authorised admin sets.
ALTER TABLE platform_fee_policies
    ADD COLUMN IF NOT EXISTS tax_percentage NUMERIC(5, 2) NOT NULL DEFAULT 2.00,
    ADD COLUMN IF NOT EXISTS tax_label VARCHAR(40) NOT NULL DEFAULT 'Tax',
    ADD COLUMN IF NOT EXISTS tax_base VARCHAR(16) NOT NULL DEFAULT 'subtotal';
ALTER TABLE platform_fee_policies DROP CONSTRAINT IF EXISTS platform_fee_policies_rates_chk;
ALTER TABLE platform_fee_policies ADD CONSTRAINT platform_fee_policies_rates_chk CHECK (
    worker_percentage BETWEEN 0 AND 100
    AND gateway_percentage BETWEEN 0 AND 100
    AND tax_percentage BETWEEN 0 AND 100
    AND tax_base IN ('subtotal', 'base_amount', 'commission')
    AND length(btrim(tax_label)) > 0
);
