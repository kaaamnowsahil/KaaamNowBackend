-- Worker withdrawal rules (admin "Withdrawals"). Single row; edited through the audited admin
-- resource, so who changed what and when lives in admin_audit_log. With no row the API uses
-- the MIN_WITHDRAWAL_MINOR env value.
CREATE TABLE IF NOT EXISTS payout_settings (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    singleton            BOOLEAN NOT NULL DEFAULT true,
    min_withdrawal_minor BIGINT NOT NULL,
    notes                VARCHAR(300) NOT NULL DEFAULT '',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT payout_settings_singleton_chk CHECK (singleton),
    CONSTRAINT payout_settings_singleton_uid UNIQUE (singleton),
    CONSTRAINT payout_settings_min_withdrawal_chk
        CHECK (min_withdrawal_minor BETWEEN 100 AND 10000000)
);
