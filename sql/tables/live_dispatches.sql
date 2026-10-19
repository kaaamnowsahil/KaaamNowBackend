-- Live request alerts sent to nearby workers (Figma "New request nearby · Accept within 04:59").
CREATE TABLE IF NOT EXISTS live_dispatches (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id          UUID NOT NULL,
    worker_profile_id UUID NOT NULL,
    radius_km         DOUBLE PRECISION NOT NULL,
    distance_km       DOUBLE PRECISION NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'offered',
    expires_at        TIMESTAMPTZ NOT NULL,
    responded_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_dispatches_shift_worker_uid UNIQUE (shift_id, worker_profile_id),
    CONSTRAINT live_dispatches_status_chk
        CHECK (status IN ('offered', 'accepted', 'declined', 'expired', 'withdrawn'))
);

CREATE INDEX IF NOT EXISTS live_dispatches_expiry_idx
    ON live_dispatches (expires_at) WHERE status = 'offered';
CREATE INDEX IF NOT EXISTS live_dispatches_worker_idx
    ON live_dispatches (worker_profile_id, status);
