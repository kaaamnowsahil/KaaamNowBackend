-- Reliability strikes (½ for cancelling inside 2h, 1 for a no-show). Count while not expired
-- or voided; thresholds live on cancellation_policies.
CREATE TABLE IF NOT EXISTS worker_strikes (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_profile_id  UUID NOT NULL,
    assignment_id      UUID,
    weight             NUMERIC(3, 1) NOT NULL,
    reason             VARCHAR(32) NOT NULL,
    expires_at         TIMESTAMPTZ NOT NULL,
    voided_at          TIMESTAMPTZ,
    voided_by_user_id  UUID,
    void_reason        VARCHAR(200),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT worker_strikes_weight_chk CHECK (weight > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS worker_strikes_assignment_uid
    ON worker_strikes (assignment_id) WHERE assignment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS worker_strikes_worker_idx
    ON worker_strikes (worker_profile_id, expires_at);
