-- One row per changed Live Work pricing field: who, previous value, new value, when.
CREATE TABLE IF NOT EXISTS live_pricing_audit (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    settings_version   INTEGER NOT NULL,
    field              VARCHAR(40) NOT NULL,
    old_value          VARCHAR(80),
    new_value          VARCHAR(80) NOT NULL,
    changed_by_user_id UUID,
    changed_by_label   VARCHAR(160) NOT NULL DEFAULT '',
    request_id         VARCHAR(64),
    changed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS live_pricing_audit_changed_idx ON live_pricing_audit (changed_at DESC);
