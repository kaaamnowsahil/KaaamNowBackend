-- Realtime push: announce changes on the kn_realtime channel (app/services/realtime/realtime_hub.py).
-- Payloads carry no data: 'shifts', or 'live:<worker_profile_id>' for that worker's Live requests.
-- Postgres delivers them on commit and drops duplicates within a transaction.
CREATE OR REPLACE FUNCTION kn_notify_shifts() RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    PERFORM pg_notify('kn_realtime', 'shifts');
    RETURN NULL;
END
$fn$;

CREATE OR REPLACE FUNCTION kn_notify_live_dispatch() RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('kn_realtime', 'live:' || OLD.worker_profile_id::text);
    ELSE
        PERFORM pg_notify('kn_realtime', 'live:' || NEW.worker_profile_id::text);
    END IF;
    RETURN NULL;
END
$fn$;

DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'shifts_realtime_notify') THEN
        CREATE TRIGGER shifts_realtime_notify
            AFTER INSERT OR UPDATE OR DELETE ON shifts
            FOR EACH STATEMENT EXECUTE FUNCTION kn_notify_shifts();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'live_dispatches_realtime_notify') THEN
        CREATE TRIGGER live_dispatches_realtime_notify
            AFTER INSERT OR UPDATE OR DELETE ON live_dispatches
            FOR EACH ROW EXECUTE FUNCTION kn_notify_live_dispatch();
    END IF;
END
$do$;
