-- Confirmed roster: one row per worker booked on a shift (Figma "Manage your confirmed roster").
CREATE TABLE IF NOT EXISTS shift_assignments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id             UUID NOT NULL,
    worker_profile_id    UUID NOT NULL,
    source               VARCHAR(16) NOT NULL,
    dispatch_id          UUID,
    application_id       UUID,
    status               VARCHAR(16) NOT NULL DEFAULT 'confirmed',
    hourly_rate_minor    BIGINT NOT NULL,
    confirmed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    travel_started_at    TIMESTAMPTZ,
    cancelled_at         TIMESTAMPTZ,
    cancelled_by_user_id UUID,
    cancel_reason        VARCHAR(200),
    late_cancellation    BOOLEAN NOT NULL DEFAULT false,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shift_assignments_source_chk CHECK (source IN ('live', 'scheduled')),
    CONSTRAINT shift_assignments_status_chk CHECK (status IN (
        'confirmed', 'en_route', 'checked_in', 'checked_out', 'approved', 'no_show', 'cancelled'
    ))
);

-- A worker holds at most one live (non-cancelled) seat per shift.
CREATE UNIQUE INDEX IF NOT EXISTS shift_assignments_one_seat_per_worker_uid
    ON shift_assignments (shift_id, worker_profile_id) WHERE status <> 'cancelled';
CREATE INDEX IF NOT EXISTS shift_assignments_shift_status_idx
    ON shift_assignments (shift_id, status);
CREATE INDEX IF NOT EXISTS shift_assignments_worker_status_idx
    ON shift_assignments (worker_profile_id, status);
