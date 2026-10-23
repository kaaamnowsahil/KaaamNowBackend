CREATE TABLE IF NOT EXISTS account_deletion_holds (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id    UUID NOT NULL,
    basis         VARCHAR(32) NOT NULL,
    reason        VARCHAR(1000) NOT NULL,
    reference     VARCHAR(200),
    expires_at    TIMESTAMPTZ NOT NULL,
    created_by    UUID,
    released_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_deletion_hold_basis_chk CHECK (basis IN (
        'pending_booking', 'pending_payment', 'refund', 'dispute',
        'complaint', 'legal_obligation', 'fraud_investigation'
    ))
);

CREATE INDEX IF NOT EXISTS account_deletion_holds_request_idx
    ON account_deletion_holds (request_id, expires_at)
    WHERE released_at IS NULL;
