-- Work / business types (Figma: Hospitality, Retail, Events, Delivery).
CREATE TABLE IF NOT EXISTS work_categories (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug       VARCHAR(64) NOT NULL,
    name       VARCHAR(120) NOT NULL,
    icon       VARCHAR(64) NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT work_categories_slug_uid UNIQUE (slug)
);
