-- "Message Aarav": chat between the business and one booked worker.
CREATE TABLE IF NOT EXISTS assignment_messages (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id  UUID NOT NULL,
    sender_user_id UUID NOT NULL,
    body           VARCHAR(1000) NOT NULL,
    read_at        TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS assignment_messages_assignment_idx
    ON assignment_messages (assignment_id, created_at);
