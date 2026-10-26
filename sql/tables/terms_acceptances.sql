-- Which Terms & Conditions version (content_pages.effective_date) a user accepted per role.
-- Posting needs the business version accepted, applying needs the worker version.
CREATE TABLE IF NOT EXISTS terms_acceptances (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    audience    VARCHAR(16) NOT NULL,
    version     DATE NOT NULL,
    ip_address  VARCHAR(64),
    user_agent  VARCHAR(300),
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT terms_acceptances_audience_chk CHECK (audience IN ('worker', 'business')),
    CONSTRAINT terms_acceptances_user_version_uid UNIQUE (user_id, audience, version)
);
