-- In-app inbox + push outbox. Rows are written in the business transaction;
-- the background loop delivers pending pushes (push_status) afterwards.
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    kind        VARCHAR(48) NOT NULL,
    title       VARCHAR(160) NOT NULL,
    body        VARCHAR(500) NOT NULL DEFAULT '',
    data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    read_at     TIMESTAMPTZ,
    push_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    pushed_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notifications_push_status_chk
        CHECK (push_status IN ('pending', 'sent', 'skipped', 'failed'))
);

CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_unread_idx ON notifications (user_id) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS notifications_push_pending_idx ON notifications (created_at)
    WHERE push_status = 'pending';
