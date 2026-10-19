-- Verified provider webhooks, deduplicated by (provider, event_id).
CREATE TABLE IF NOT EXISTS payment_webhook_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     VARCHAR(32) NOT NULL,
    event_id     VARCHAR(128) NOT NULL,
    event_type   VARCHAR(64) NOT NULL,
    payload      JSONB NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT payment_webhook_events_provider_event_uid UNIQUE (provider, event_id)
);
