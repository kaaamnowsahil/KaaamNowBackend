-- Search distances (admin "Search radius"). Single row; edited through the audited admin
-- resource, so who changed what and when lives in admin_audit_log. With no row the API uses
-- the LIVE_* / SCHEDULED_* / FEED_* / WORKER_MAX_* env values.
-- Live Work bookings keep the radius they started searching with (shifts.search_radius_km).
CREATE TABLE IF NOT EXISTS search_radius_settings (
    id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    singleton                    BOOLEAN NOT NULL DEFAULT true,
    live_initial_radius_km       NUMERIC(5, 1) NOT NULL,
    live_max_radius_km           NUMERIC(5, 1) NOT NULL,
    scheduled_notify_radius_km   NUMERIC(5, 1) NOT NULL,
    feed_radius_km               NUMERIC(5, 1) NOT NULL,
    worker_max_shift_distance_km NUMERIC(5, 1) NOT NULL,
    notes                        VARCHAR(300) NOT NULL DEFAULT '',
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT search_radius_settings_singleton_chk CHECK (singleton),
    CONSTRAINT search_radius_settings_singleton_uid UNIQUE (singleton),
    CONSTRAINT search_radius_settings_range_chk CHECK (
        live_initial_radius_km BETWEEN 0.5 AND 100
        AND live_max_radius_km BETWEEN 0.5 AND 100
        AND scheduled_notify_radius_km BETWEEN 0.5 AND 100
        AND feed_radius_km BETWEEN 0.5 AND 100
        AND worker_max_shift_distance_km BETWEEN 0.5 AND 100
    ),
    CONSTRAINT search_radius_settings_live_order_chk
        CHECK (live_initial_radius_km <= live_max_radius_km),
    CONSTRAINT search_radius_settings_feed_order_chk
        CHECK (feed_radius_km <= worker_max_shift_distance_km)
);
