-- Booking-specific arrival code: shown only to the Business, entered by the assigned Worker to
-- start work. Expires, and locks after too many wrong attempts until the Business issues a new one.
CREATE TABLE IF NOT EXISTS live_arrival_codes (
    assignment_id   UUID PRIMARY KEY,
    shift_id        UUID NOT NULL,
    code            VARCHAR(8) NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    failed_attempts SMALLINT NOT NULL DEFAULT 0,
    locked_at       TIMESTAMPTZ,
    verified_at     TIMESTAMPTZ,
    issued_count    SMALLINT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_arrival_codes_attempts_chk CHECK (failed_attempts >= 0)
);
