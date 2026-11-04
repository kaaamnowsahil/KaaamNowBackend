-- Live Work pricing & charges (admin "Live Work Pricing & Charges"). Versioned: saving creates a
-- new active version; bookings snapshot the version they were priced with (live_booking_pricing).
-- tax_base: 'subtotal' = base amount + business commission, 'base_amount', or 'commission'.
CREATE TABLE IF NOT EXISTS live_pricing_settings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version                 INTEGER NOT NULL,
    commission_pct          NUMERIC(5, 2) NOT NULL,
    tax_pct                 NUMERIC(5, 2) NOT NULL,
    tax_label               VARCHAR(40) NOT NULL DEFAULT 'Tax',
    tax_base                VARCHAR(16) NOT NULL DEFAULT 'subtotal',
    extension_surcharge_pct NUMERIC(5, 2) NOT NULL,
    is_active               BOOLEAN NOT NULL DEFAULT false,
    effective_from          TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by_user_id      UUID,
    changed_by_label        VARCHAR(160) NOT NULL DEFAULT '',
    notes                   VARCHAR(300) NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_pricing_settings_version_uid UNIQUE (version),
    CONSTRAINT live_pricing_settings_pct_chk CHECK (
        commission_pct BETWEEN 0 AND 100
        AND tax_pct BETWEEN 0 AND 100
        AND extension_surcharge_pct BETWEEN 0 AND 100
    ),
    CONSTRAINT live_pricing_settings_tax_base_chk
        CHECK (tax_base IN ('subtotal', 'base_amount', 'commission'))
);

CREATE UNIQUE INDEX IF NOT EXISTS live_pricing_settings_one_active_uid
    ON live_pricing_settings (is_active) WHERE is_active;

-- Search + retry rules (admin-editable, versioned with the rates; a booking keeps the version
-- it was priced with). Nobody accepted → the Business may add one of boost_options_minor to the
-- pay and search again, up to max_search_rounds searches, choosing within retry_choice_minutes.
ALTER TABLE live_pricing_settings
    ADD COLUMN IF NOT EXISTS search_timeout_minutes SMALLINT NOT NULL DEFAULT 30,
    ADD COLUMN IF NOT EXISTS max_search_rounds SMALLINT NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS retry_choice_minutes SMALLINT NOT NULL DEFAULT 10,
    ADD COLUMN IF NOT EXISTS boost_options_minor BIGINT[] NOT NULL DEFAULT '{1000,2000,3000}';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'live_pricing_settings_search_chk'
    ) THEN
        ALTER TABLE live_pricing_settings ADD CONSTRAINT live_pricing_settings_search_chk CHECK (
            search_timeout_minutes BETWEEN 5 AND 120
            AND max_search_rounds BETWEEN 1 AND 5
            AND retry_choice_minutes BETWEEN 2 AND 60
            AND cardinality(boost_options_minor) BETWEEN 1 AND 5
        );
    END IF;
END $$;
