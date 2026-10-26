"""SQL for the generic admin CRUD layer and dashboard metrics.

Templates marked ``{...}`` only ever receive identifiers that were whitelisted against the
resource registry *and* ``information_schema`` and then quoted with ``quote_ident``;
every user-supplied value is bound as a ``$n`` parameter.
"""

from __future__ import annotations

LIST_TABLE_COLUMNS = """
SELECT c.table_name,
       c.column_name,
       c.data_type,
       c.udt_name,
       c.is_nullable = 'YES' AS is_nullable,
       c.column_default IS NOT NULL OR c.is_identity = 'YES' AS has_default,
       c.is_generated = 'ALWAYS' AS is_generated,
       c.character_maximum_length AS max_length
FROM information_schema.columns c
WHERE c.table_schema = current_schema() AND c.table_name = ANY($1::text[])
ORDER BY c.table_name, c.ordinal_position
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
