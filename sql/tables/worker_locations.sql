-- Latest live location only (no history). Deleted when the worker goes unavailable.
CREATE TABLE IF NOT EXISTS worker_locations (
    worker_profile_id UUID PRIMARY KEY,
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    accuracy_m        INTEGER,
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS worker_locations_geo_idx ON worker_locations (latitude, longitude);
CREATE INDEX IF NOT EXISTS worker_locations_recorded_at_idx ON worker_locations (recorded_at);
