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

CREATE UNIQUE INDEX IF NOT EXISTS platform_fee_policies_one_active_uid
    ON platform_fee_policies (is_active) WHERE is_active;
