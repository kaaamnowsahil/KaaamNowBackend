-- Completion code for one booked seat (Shift or Live Work, hourly or task): issued when the
-- Worker starts work, shown only to the Business, entered by the Worker to finish. Locks after
-- too many wrong attempts until the Business issues a new one. Never expires while working.
CREATE TABLE IF NOT EXISTS assignment_completion_codes (
    assignment_id   UUID PRIMARY KEY,
    shift_id        UUID NOT NULL,
    code            VARCHAR(8) NOT NULL,
    failed_attempts SMALLINT NOT NULL DEFAULT 0,
    locked_at       TIMESTAMPTZ,
    verified_at     TIMESTAMPTZ,
    issued_count    SMALLINT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT assignment_completion_codes_attempts_chk CHECK (failed_attempts >= 0),
    CONSTRAINT assignment_completion_codes_issued_chk CHECK (issued_count >= 1)
);

CREATE INDEX IF NOT EXISTS assignment_completion_codes_shift_idx
    ON assignment_completion_codes (shift_id);

-- Workers already checked in when this table was introduced get a code too (idempotent).
INSERT INTO assignment_completion_codes (assignment_id, shift_id, code)
SELECT a.id, a.shift_id,
       lpad((abs(('x' || substr(md5(gen_random_uuid()::text), 1, 8))::bit(32)::int)
             % 1000000)::text, 6, '0')
FROM shift_assignments a
WHERE a.status = 'checked_in'
ON CONFLICT (assignment_id) DO NOTHING;
