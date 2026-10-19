-- Scheduled shifts: worker applies → business selects → worker confirms.
-- Figma "Application submitted" / "Review your applicants" / "You've been selected".
CREATE TABLE IF NOT EXISTS shift_applications (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id          UUID NOT NULL,
    worker_profile_id UUID NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'applied',
    distance_km       DOUBLE PRECISION,
    cover_note        VARCHAR(500) NOT NULL DEFAULT '',
    confirm_by        TIMESTAMPTZ,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at        TIMESTAMPTZ,
    responded_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shift_applications_shift_worker_uid UNIQUE (shift_id, worker_profile_id),
    CONSTRAINT shift_applications_status_chk CHECK (status IN (
        'applied', 'selected', 'confirmed', 'declined', 'rejected', 'withdrawn', 'expired'
    ))
);

CREATE INDEX IF NOT EXISTS shift_applications_shift_status_idx
    ON shift_applications (shift_id, status);
CREATE INDEX IF NOT EXISTS shift_applications_worker_idx
    ON shift_applications (worker_profile_id, status);
CREATE INDEX IF NOT EXISTS shift_applications_confirm_by_idx
    ON shift_applications (confirm_by) WHERE status = 'selected';
