-- "Contact support" / "I need help checking in".
CREATE TABLE IF NOT EXISTS support_tickets (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,
    topic      VARCHAR(32) NOT NULL DEFAULT 'general',
    subject    VARCHAR(160) NOT NULL,
    message    TEXT NOT NULL,
    shift_id   UUID,
    status     VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT support_tickets_topic_chk
        CHECK (topic IN ('general', 'check_in', 'payment', 'payout', 'shift', 'account')),
    CONSTRAINT support_tickets_status_chk CHECK (status IN ('open', 'closed'))
);

CREATE INDEX IF NOT EXISTS support_tickets_user_idx ON support_tickets (user_id, created_at DESC);
