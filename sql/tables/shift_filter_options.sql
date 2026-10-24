CREATE TABLE IF NOT EXISTS shift_filter_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filter_type VARCHAR(32) NOT NULL,
    slug VARCHAR(64) NOT NULL,
    label VARCHAR(120) NOT NULL,
    min_value NUMERIC(10, 2),
    max_value NUMERIC(10, 2),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shift_filter_options_type_check
        CHECK (filter_type IN ('distance', 'minimum_pay', 'shift_length')),
    CONSTRAINT shift_filter_options_slug_uid UNIQUE (filter_type, slug),
    CONSTRAINT shift_filter_options_range_check
        CHECK (min_value IS NULL OR max_value IS NULL OR min_value <= max_value)
);

CREATE INDEX IF NOT EXISTS shift_filter_options_active_order_idx
    ON shift_filter_options (filter_type, is_active, sort_order);
