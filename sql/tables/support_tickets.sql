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

-- Emergency button on a booking: urgent ticket with the assignment attached (rules §10).
ALTER TABLE support_tickets
    ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS assignment_id UUID,
    ADD COLUMN IF NOT EXISTS resolution_note VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS resolved_by_user_id UUID,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE support_tickets DROP CONSTRAINT IF EXISTS support_tickets_topic_chk;
ALTER TABLE support_tickets ADD CONSTRAINT support_tickets_topic_chk CHECK (
    topic IN ('general', 'check_in', 'payment', 'payout', 'shift', 'account', 'emergency')
);
ALTER TABLE support_tickets DROP CONSTRAINT IF EXISTS support_tickets_status_chk;
ALTER TABLE support_tickets ADD CONSTRAINT support_tickets_status_chk
    CHECK (status IN ('open', 'in_progress', 'closed'));
ALTER TABLE support_tickets DROP CONSTRAINT IF EXISTS support_tickets_priority_chk;
ALTER TABLE support_tickets ADD CONSTRAINT support_tickets_priority_chk
    CHECK (priority IN ('normal', 'urgent'));

CREATE INDEX IF NOT EXISTS support_tickets_queue_idx
    ON support_tickets (priority, status, created_at);
