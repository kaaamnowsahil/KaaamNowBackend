-- Worker withdrawal destinations (Figma "Withdraw to": UPI ID, Paytm, bank account).
CREATE TABLE IF NOT EXISTS payout_accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_profile_id   UUID NOT NULL,
    account_type        VARCHAR(16) NOT NULL,
    upi_id              VARCHAR(100),
    paytm_phone         VARCHAR(16),
    bank_account_number VARCHAR(34),
    bank_ifsc           VARCHAR(11),
    account_holder_name VARCHAR(120) NOT NULL DEFAULT '',
    is_default          BOOLEAN NOT NULL DEFAULT false,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT payout_accounts_type_chk CHECK (account_type IN ('upi', 'paytm', 'bank')),
    CONSTRAINT payout_accounts_fields_chk CHECK (
        (account_type = 'upi' AND upi_id IS NOT NULL)
        OR (account_type = 'paytm' AND paytm_phone IS NOT NULL)
        OR (account_type = 'bank' AND bank_account_number IS NOT NULL AND bank_ifsc IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS payout_accounts_one_default_uid
    ON payout_accounts (worker_profile_id) WHERE is_default AND is_active;
CREATE INDEX IF NOT EXISTS payout_accounts_worker_idx
    ON payout_accounts (worker_profile_id) WHERE is_active;
