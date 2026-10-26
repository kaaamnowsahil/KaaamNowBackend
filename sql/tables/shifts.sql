-- A business posting: live (start now, first-come) or scheduled (apply → select).
-- Figma "Tell us about the work" / "When is the shift?".
CREATE TABLE IF NOT EXISTS shifts (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_profile_id       UUID NOT NULL,
    category_id               UUID NOT NULL,
    shift_type                VARCHAR(16) NOT NULL,
    status                    VARCHAR(16) NOT NULL DEFAULT 'draft',
    job_title                 VARCHAR(120) NOT NULL,
    responsibilities          TEXT NOT NULL DEFAULT '',
    requirements              TEXT NOT NULL DEFAULT '',
    workers_required          SMALLINT NOT NULL,
    hourly_rate_minor         BIGINT NOT NULL,
    currency                  CHAR(3) NOT NULL DEFAULT 'INR',
    starts_at                 TIMESTAMPTZ NOT NULL,
    ends_at                   TIMESTAMPTZ NOT NULL,
    break_minutes             SMALLINT NOT NULL DEFAULT 0,
    workplace_name            VARCHAR(160) NOT NULL DEFAULT '',
    address_text              VARCHAR(500) NOT NULL,
    latitude                  DOUBLE PRECISION,
    longitude                 DOUBLE PRECISION,
    arrival_instructions      TEXT NOT NULL DEFAULT '',
    site_contact_name         VARCHAR(120) NOT NULL DEFAULT '',
    check_in_code             VARCHAR(8) NOT NULL,
    cancellation_cutoff_hours SMALLINT NOT NULL DEFAULT 12,
    search_radius_km          DOUBLE PRECISION,
    max_search_radius_km      DOUBLE PRECISION,
    search_started_at         TIMESTAMPTZ,
    search_expires_at         TIMESTAMPTZ,
    radius_expanded_at        TIMESTAMPTZ,
    fee_policy_version        INTEGER,
    fee_percentage            NUMERIC(5, 2),
    published_at              TIMESTAMPTZ,
    filled_at                 TIMESTAMPTZ,
    started_at                TIMESTAMPTZ,
    completed_at              TIMESTAMPTZ,
    cancelled_at              TIMESTAMPTZ,
    cancel_reason             VARCHAR(200),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shifts_shift_type_chk CHECK (shift_type IN ('live', 'scheduled')),
    CONSTRAINT shifts_status_chk CHECK (status IN (
        'draft', 'searching', 'open', 'filled', 'in_progress',
        'completed', 'expired', 'cancelled'
    )),
    CONSTRAINT shifts_workers_required_chk CHECK (workers_required BETWEEN 1 AND 100),
    CONSTRAINT shifts_hourly_rate_chk CHECK (hourly_rate_minor > 0),
    CONSTRAINT shifts_time_window_chk CHECK (ends_at > starts_at),
    CONSTRAINT shifts_break_minutes_chk CHECK (break_minutes >= 0)
);

ALTER TABLE shifts
    ALTER COLUMN latitude DROP NOT NULL,
    ALTER COLUMN longitude DROP NOT NULL;

-- ``awaiting_payment``: a published scheduled shift whose deposit is not paid yet.
ALTER TABLE shifts DROP CONSTRAINT IF EXISTS shifts_status_chk;
ALTER TABLE shifts ADD CONSTRAINT shifts_status_chk CHECK (status IN (
    'draft', 'awaiting_payment', 'searching', 'open', 'filled', 'in_progress',
    'completed', 'expired', 'cancelled'
));

-- Snapshotted from platform_fee_policies at publish, next to fee_percentage (business commission).
ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS worker_fee_percentage NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS gateway_fee_percentage NUMERIC(5, 2);

CREATE INDEX IF NOT EXISTS shifts_business_profile_idx
    ON shifts (business_profile_id, starts_at DESC);
CREATE INDEX IF NOT EXISTS shifts_discovery_idx ON shifts (shift_type, status, starts_at);
CREATE INDEX IF NOT EXISTS shifts_geo_idx ON shifts (latitude, longitude)
    WHERE status IN ('searching', 'open');

-- Promo code entered at posting; its discount applies to the deposit and final invoices.
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS promo_code_id UUID;
