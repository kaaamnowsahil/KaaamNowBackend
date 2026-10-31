-- Append-only worker money ledger. Available balance = SUM(amount_minor).
-- Credits: shift_earning, withdrawal_reversal. Debits (negative): withdrawal.
CREATE TABLE IF NOT EXISTS earning_ledger_entries (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_profile_id UUID NOT NULL,
    entry_type        VARCHAR(24) NOT NULL,
    amount_minor      BIGINT NOT NULL,
    currency          CHAR(3) NOT NULL,
    assignment_id     UUID,
    invoice_id        UUID,
    withdrawal_id     UUID,
    description       VARCHAR(200) NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT earning_ledger_entries_type_chk
        CHECK (entry_type IN ('shift_earning', 'withdrawal', 'withdrawal_reversal')),
    CONSTRAINT earning_ledger_entries_sign_chk CHECK (
        (entry_type = 'withdrawal' AND amount_minor < 0)
        OR (entry_type <> 'withdrawal' AND amount_minor > 0)
    )
);

-- This file runs on every boot against live data: only ever widen these checks, in one step.
-- ``commission`` (negative): worker commission deducted from a shift earning.
-- ``adjustment`` (negative): platform share when the business stops work early (rules §8).
-- ``promo_credit`` (positive): worker promo code applied to a payout's commission.
-- ``fee_waiver`` (positive): admin refunded a fee / adjustment for one booking (rules §10).
-- Cancellation money: ``cancellation_fee`` (negative, may push the balance below zero; it is
-- recovered from later earnings) and ``cancellation_compensation`` (business cancelled late).
ALTER TABLE earning_ledger_entries ALTER COLUMN entry_type TYPE VARCHAR(32);
ALTER TABLE earning_ledger_entries DROP CONSTRAINT IF EXISTS earning_ledger_entries_type_chk;
ALTER TABLE earning_ledger_entries ADD CONSTRAINT earning_ledger_entries_type_chk CHECK (
    entry_type IN (
        'shift_earning', 'withdrawal', 'withdrawal_reversal', 'commission',
        'cancellation_fee', 'cancellation_compensation', 'adjustment', 'promo_credit',
        'fee_waiver'
    )
);
ALTER TABLE earning_ledger_entries DROP CONSTRAINT IF EXISTS earning_ledger_entries_sign_chk;
ALTER TABLE earning_ledger_entries ADD CONSTRAINT earning_ledger_entries_sign_chk CHECK (
    (entry_type IN ('withdrawal', 'commission', 'cancellation_fee', 'adjustment')
        AND amount_minor < 0)
    OR (entry_type NOT IN ('withdrawal', 'commission', 'cancellation_fee', 'adjustment')
        AND amount_minor > 0)
);

-- Idempotency: one earning per assignment, one debit / reversal per withdrawal.
CREATE UNIQUE INDEX IF NOT EXISTS earning_ledger_entries_assignment_uid
    ON earning_ledger_entries (entry_type, assignment_id) WHERE assignment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS earning_ledger_entries_withdrawal_uid
    ON earning_ledger_entries (entry_type, withdrawal_id) WHERE withdrawal_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS earning_ledger_entries_worker_idx
    ON earning_ledger_entries (worker_profile_id, created_at DESC);
