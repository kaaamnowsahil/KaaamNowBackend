-- Audit trail of every shift status transition.
CREATE TABLE IF NOT EXISTS shift_status_history (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id      UUID NOT NULL,
    from_status   VARCHAR(16) NOT NULL,
    to_status     VARCHAR(16) NOT NULL,
    actor_user_id UUID,
    reason        VARCHAR(200) NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS shift_status_history_shift_idx
    ON shift_status_history (shift_id, created_at);
