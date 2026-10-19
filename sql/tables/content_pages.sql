-- Terms & Conditions per audience (Figma worker + business variants).
CREATE TABLE IF NOT EXISTS content_pages (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug           VARCHAR(64) NOT NULL,
    audience       VARCHAR(16) NOT NULL,
    title          VARCHAR(160) NOT NULL,
    body_markdown  TEXT NOT NULL,
    effective_date DATE NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT content_pages_slug_audience_uid UNIQUE (slug, audience),
    CONSTRAINT content_pages_audience_chk CHECK (audience IN ('worker', 'business', 'all'))
);
