CREATE TABLE IF NOT EXISTS account_deletion_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id  UUID NOT NULL,
    actor_user_id UUID,
    event_type  VARCHAR(32) NOT NULL,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_deletion_event_type_chk CHECK (event_type IN (
        'requested', 'approved', 'hold_added', 'hold_released',
        'hold_expired', 'completed'
    ))
);

CREATE INDEX IF NOT EXISTS account_deletion_events_request_idx
    ON account_deletion_events (request_id, created_at);
