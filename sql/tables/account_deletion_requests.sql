CREATE SEQUENCE IF NOT EXISTS account_deletion_phone_seq START WITH 1;

CREATE TABLE IF NOT EXISTS account_deletion_requests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    status       VARCHAR(16) NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_deletion_status_chk
        CHECK (status IN ('pending', 'approved', 'on_hold', 'completed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS account_deletion_one_open_request_uid
    ON account_deletion_requests (user_id)
    WHERE status IN ('pending', 'approved', 'on_hold');
CREATE INDEX IF NOT EXISTS account_deletion_requests_queue_idx
    ON account_deletion_requests (status, requested_at);
