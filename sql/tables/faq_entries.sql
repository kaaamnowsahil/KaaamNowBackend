-- FAQ & Help entries per audience.
CREATE TABLE IF NOT EXISTS faq_entries (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audience   VARCHAR(16) NOT NULL,
    question   VARCHAR(300) NOT NULL,
    answer     TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT faq_entries_audience_question_uid UNIQUE (audience, question),
    CONSTRAINT faq_entries_audience_chk CHECK (audience IN ('worker', 'business', 'all'))
);

-- Stable id the app uses for expand/collapse state and deep links.
ALTER TABLE faq_entries ADD COLUMN IF NOT EXISTS slug VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS faq_entries_audience_slug_uid
    ON faq_entries (audience, slug) WHERE slug IS NOT NULL;
