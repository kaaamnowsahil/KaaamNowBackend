-- Admin changes to one booking's fees / strikes / vouchers, with the reason (rules §10).
CREATE TABLE IF NOT EXISTS admin_overrides (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id     UUID NOT NULL,
    support_ticket_id UUID,
    action            VARCHAR(32) NOT NULL,
    amount_minor      BIGINT NOT NULL DEFAULT 0,
    reason            VARCHAR(500) NOT NULL,
    admin_user_id     UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT admin_overrides_action_chk CHECK (action IN (
        'waive_worker_fee', 'void_strike', 'unban_worker', 'revoke_voucher', 'refund_business'
    ))
);

CREATE INDEX IF NOT EXISTS admin_overrides_assignment_idx
    ON admin_overrides (assignment_id, created_at DESC);
