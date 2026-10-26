-- "Extend this shift?": business asks for extra minutes, worker accepts. Paid as overtime.
CREATE TABLE IF NOT EXISTS shift_extensions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id        UUID NOT NULL,
    extra_minutes        INTEGER NOT NULL,
    status               VARCHAR(16) NOT NULL DEFAULT 'requested',
    requested_by_user_id UUID,
    requested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at         TIMESTAMPTZ,
    CONSTRAINT shift_extensions_minutes_chk CHECK (extra_minutes > 0),
    CONSTRAINT shift_extensions_status_chk
        CHECK (status IN ('requested', 'accepted', 'declined', 'cancelled', 'expired'))
);

-- At most one open request per assignment.
CREATE UNIQUE INDEX IF NOT EXISTS shift_extensions_one_open_uid
    ON shift_extensions (assignment_id) WHERE status = 'requested';
CREATE INDEX IF NOT EXISTS shift_extensions_assignment_idx
    ON shift_extensions (assignment_id, requested_at DESC);
