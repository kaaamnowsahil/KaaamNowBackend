-- Who changed which pricing / coupon / cancellation record through the admin data editor, with
-- the values before and after. Written in the same transaction as the change.
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource      VARCHAR(64) NOT NULL,
    record_id     VARCHAR(200) NOT NULL,
    action        VARCHAR(16) NOT NULL,
    actor_user_id UUID,
    old_values    TEXT,
    new_values    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT admin_audit_log_action_chk CHECK (action IN ('create', 'update', 'delete'))
);

CREATE INDEX IF NOT EXISTS admin_audit_log_record_idx
    ON admin_audit_log (resource, record_id, created_at);
CREATE INDEX IF NOT EXISTS admin_audit_log_created_idx ON admin_audit_log (created_at DESC);
