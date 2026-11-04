"""SQL for the generic admin CRUD layer and dashboard metrics.

Templates marked ``{...}`` only ever receive identifiers that were whitelisted against the
resource registry *and* the database catalog and then quoted with ``quote_ident``;
every user-supplied value is bound as a ``$n`` parameter.
"""

from __future__ import annotations

# Same values as information_schema.columns, read from pg_catalog directly: the
# information_schema view runs privilege checks per column and takes seconds on Neon.
LIST_TABLE_COLUMNS = """
SELECT c.relname::text AS table_name,
       a.attname::text AS column_name,
       CASE
           WHEN coalesce(bt.typelem, t.typelem) <> 0 AND coalesce(bt.typlen, t.typlen) = -1
               THEN 'ARRAY'
           WHEN coalesce(nbt.nspname, nt.nspname) = 'pg_catalog'
               THEN format_type(coalesce(bt.oid, t.oid), NULL)
           ELSE 'USER-DEFINED'
       END AS data_type,
       coalesce(bt.typname, t.typname)::text AS udt_name,
       NOT (a.attnotnull OR (t.typtype = 'd' AND t.typnotnull)) AS is_nullable,
       (a.atthasdef AND a.attgenerated = '') OR a.attidentity <> '' AS has_default,
       a.attgenerated <> '' AS is_generated,
       CASE
           WHEN coalesce(bt.typname, t.typname) IN ('bpchar', 'varchar')
                AND (CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END) <> -1
               THEN (CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END) - 4
           WHEN coalesce(bt.typname, t.typname) IN ('bit', 'varbit')
                AND (CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END) <> -1
               THEN (CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END)
       END AS max_length
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
JOIN pg_namespace nt ON nt.oid = t.typnamespace
LEFT JOIN pg_type bt ON t.typtype = 'd' AND bt.oid = t.typbasetype
LEFT JOIN pg_namespace nbt ON nbt.oid = bt.typnamespace
WHERE n.nspname = current_schema()
  AND c.relname = ANY($1::text[])
  AND c.relkind IN ('r', 'v', 'f', 'p', 'm')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

SELECT_PAGE = "SELECT {columns} FROM {table}{where} ORDER BY {order} LIMIT {limit} OFFSET {offset}"
SELECT_ALL = "SELECT {columns} FROM {table}{where} ORDER BY {order} LIMIT {limit}"
COUNT_ROWS = "SELECT count(*) FROM {table}{where}"
SELECT_ONE = "SELECT {columns} FROM {table} WHERE {key}"
INSERT_ROW = "INSERT INTO {table} ({columns}) VALUES ({values}) RETURNING {returning}"
INSERT_DEFAULTS = "INSERT INTO {table} DEFAULT VALUES RETURNING {returning}"
UPDATE_ROW = "UPDATE {table} SET {assignments} WHERE {key} RETURNING {returning}"
DELETE_ROW = "DELETE FROM {table} WHERE {key} RETURNING 1"

WHERE_PREFIX = " WHERE "
AND_JOIN = " AND "
OR_JOIN = " OR "
COMMA_JOIN = ", "
EQUALS_PARAM = "{column} = ${n}"
IS_NULL = "{column} IS NULL"
SEARCH_CLAUSE = "{column}::text ILIKE ${n} ESCAPE '\\'"
ORDER_ASC = "{column} ASC"
ORDER_DESC = "{column} DESC NULLS LAST"
SET_NOW = "{column} = now()"
SET_FALSE = "{column} = false"
PARAM = "${n}"

METRICS_SCALARS = """
SELECT
    (SELECT count(*) FROM users) AS users_total,
    (SELECT count(*) FROM users WHERE is_active) AS users_active,
    (SELECT count(*) FROM worker_profiles) AS workers_total,
    (SELECT count(*) FROM business_profiles) AS businesses_total,
    (SELECT count(*) FROM shifts) AS shifts_total,
    (SELECT count(*) FROM support_tickets WHERE status = $1) AS open_support_tickets,
    (SELECT count(*) FROM withdrawals WHERE status = ANY($2::text[])) AS pending_withdrawals,
    (SELECT COALESCE(sum(amount_minor), 0) FROM withdrawals WHERE status = ANY($2::text[]))
        AS pending_withdrawals_minor,
    (SELECT COALESCE(sum(amount_minor), 0) FROM withdrawals WHERE status = $3)
        AS total_paid_out_minor,
    (SELECT COALESCE(sum(total_minor), 0) FROM shift_invoices
     WHERE status = $4 AND invoice_kind = 'final')
        AS invoiced_paid_minor,
    (SELECT COALESCE(sum(platform_fee_minor), 0) FROM shift_invoices
     WHERE status = $4 AND invoice_kind = 'final')
        AS platform_fees_minor,
    (SELECT COALESCE(sum(amount_minor), 0) FROM payments WHERE status = $5)
        AS payments_succeeded_minor
"""

WORKERS_BY_VERIFICATION = """
SELECT verification_status AS key, count(*) AS count
FROM worker_profiles GROUP BY verification_status ORDER BY verification_status
"""

BUSINESSES_BY_VERIFICATION = """
SELECT verification_status AS key, count(*) AS count
FROM business_profiles GROUP BY verification_status ORDER BY verification_status
"""

SHIFTS_BY_STATUS = """
SELECT status AS key, count(*) AS count FROM shifts GROUP BY status ORDER BY status
"""

INSERT_AUDIT = """
INSERT INTO admin_audit_log (resource, record_id, action, actor_user_id, old_values, new_values)
VALUES ($1, $2, $3, $4, $5, $6)
"""
