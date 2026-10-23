-- Check-in / check-out per assignment; business reviews payable minutes.
-- Figma "Ready to check in?" / "Finish your shift?" / "Review attendance".
CREATE TABLE IF NOT EXISTS attendance_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id       UUID NOT NULL,
    checked_in_at       TIMESTAMPTZ NOT NULL,
    check_in_latitude   DOUBLE PRECISION,
    check_in_longitude  DOUBLE PRECISION,
    check_in_distance_m INTEGER NOT NULL,
    checked_out_at      TIMESTAMPTZ,
    check_out_latitude  DOUBLE PRECISION,
    check_out_longitude DOUBLE PRECISION,
    worker_note         VARCHAR(500) NOT NULL DEFAULT '',
    recorded_minutes    INTEGER,
    approved_minutes    INTEGER,
    business_note       VARCHAR(500) NOT NULL DEFAULT '',
    approved_at         TIMESTAMPTZ,
    approved_by_user_id UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT attendance_records_assignment_uid UNIQUE (assignment_id),
    CONSTRAINT attendance_records_minutes_chk CHECK (
        (recorded_minutes IS NULL OR recorded_minutes >= 0)
        AND (approved_minutes IS NULL OR approved_minutes >= 0)
    )
);

ALTER TABLE attendance_records
    ALTER COLUMN check_in_latitude DROP NOT NULL,
    ALTER COLUMN check_in_longitude DROP NOT NULL;
