-- Idempotent FK helper used by sql/relations/*.sql (safe to re-run on every boot).
CREATE OR REPLACE FUNCTION kn_add_foreign_key(
    p_table      TEXT,
    p_constraint TEXT,
    p_column     TEXT,
    p_ref_table  TEXT,
    p_ref_column TEXT,
    p_on_delete  TEXT
) RETURNS VOID
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF p_on_delete NOT IN ('CASCADE', 'RESTRICT', 'SET NULL') THEN
        RAISE EXCEPTION 'unsupported ON DELETE action: %', p_on_delete;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = p_constraint) THEN
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I (%I) ON DELETE %s',
            p_table, p_constraint, p_column, p_ref_table, p_ref_column, p_on_delete
        );
    END IF;
END
$fn$;
