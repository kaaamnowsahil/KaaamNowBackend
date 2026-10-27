"""asyncpg persistence for the generic admin CRUD layer.

Callers pass identifiers that were already whitelisted by the admin service; this module
quotes every identifier and binds every value as a parameter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import asyncpg

from app.repositories.admin.admin_queries import (
    AND_JOIN,
    BUSINESSES_BY_VERIFICATION,
    COMMA_JOIN,
    COUNT_ROWS,
    DELETE_ROW,
    EQUALS_PARAM,
    INSERT_AUDIT,
    INSERT_DEFAULTS,
    INSERT_ROW,
    IS_NULL,
    LIST_TABLE_COLUMNS,
    METRICS_SCALARS,
    OR_JOIN,
    ORDER_ASC,
    ORDER_DESC,
    PARAM,
    SEARCH_CLAUSE,
    SELECT_ALL,
    SELECT_ONE,
    SELECT_PAGE,
    SET_FALSE,
    SET_NOW,
    SHIFTS_BY_STATUS,
    UPDATE_ROW,
    WHERE_PREFIX,
    WORKERS_BY_VERIFICATION,
)

_LIKE_ESCAPES = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _column_list(columns: Sequence[str]) -> str:
    return COMMA_JOIN.join(quote_ident(c) for c in columns)


class _Params:
    """Accumulates bound values and hands out ``$n`` placeholders."""

    def __init__(self) -> None:
        self.values: list[Any] = []

    def add(self, value: Any) -> int:
        self.values.append(value)
        return len(self.values)


def _key_clause(key: Mapping[str, Any], params: _Params) -> str:
    return AND_JOIN.join(
        EQUALS_PARAM.format(column=quote_ident(col), n=params.add(val)) for col, val in key.items()
    )


def _where(
    filters: Sequence[tuple[str, Any]],
    search_columns: Sequence[str],
    search_term: str | None,
    params: _Params,
) -> str:
    clauses: list[str] = []
    for column, value in filters:
        if value is None:
            clauses.append(IS_NULL.format(column=quote_ident(column)))
        else:
            clauses.append(EQUALS_PARAM.format(column=quote_ident(column), n=params.add(value)))
    if search_term and search_columns:
        n = params.add(f"%{search_term.translate(_LIKE_ESCAPES)}%")
        ors = OR_JOIN.join(SEARCH_CLAUSE.format(column=quote_ident(c), n=n) for c in search_columns)
        clauses.append(f"({ors})")
    return WHERE_PREFIX + AND_JOIN.join(clauses) if clauses else ""


def _order(order: Sequence[tuple[str, bool]]) -> str:
    return COMMA_JOIN.join(
        (ORDER_DESC if desc else ORDER_ASC).format(column=quote_ident(col)) for col, desc in order
    )


async def fetch_table_columns(conn: asyncpg.Connection, tables: list[str]) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_TABLE_COLUMNS, tables)


async def list_rows(
    conn: asyncpg.Connection,
    *,
    table: str,
    columns: Sequence[str],
    filters: Sequence[tuple[str, Any]],
    search_columns: Sequence[str],
    search_term: str | None,
    order: Sequence[tuple[str, bool]],
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    params = _Params()
    where = _where(filters, search_columns, search_term, params)
    total = await conn.fetchval(
        COUNT_ROWS.format(table=quote_ident(table), where=where), *params.values
    )
    sql = SELECT_PAGE.format(
        columns=_column_list(columns),
        table=quote_ident(table),
        where=where,
        order=_order(order),
        limit=PARAM.format(n=params.add(limit)),
        offset=PARAM.format(n=params.add(offset)),
    )
    rows = await conn.fetch(sql, *params.values)
    return rows, int(total)


async def export_rows(
    conn: asyncpg.Connection,
    *,
    table: str,
    columns: Sequence[str],
    filters: Sequence[tuple[str, Any]],
    search_columns: Sequence[str],
    search_term: str | None,
    order: Sequence[tuple[str, bool]],
    limit: int,
) -> list[asyncpg.Record]:
    params = _Params()
    where = _where(filters, search_columns, search_term, params)
    sql = SELECT_ALL.format(
        columns=_column_list(columns),
        table=quote_ident(table),
        where=where,
        order=_order(order),
        limit=PARAM.format(n=params.add(limit)),
    )
    return await conn.fetch(sql, *params.values)


async def get_row(
    conn: asyncpg.Connection, *, table: str, columns: Sequence[str], key: Mapping[str, Any]
) -> asyncpg.Record | None:
    params = _Params()
    sql = SELECT_ONE.format(
        columns=_column_list(columns), table=quote_ident(table), key=_key_clause(key, params)
    )
    return await conn.fetchrow(sql, *params.values)


async def insert_row(
    conn: asyncpg.Connection,
    *,
    table: str,
    values: Mapping[str, Any],
    returning: Sequence[str],
) -> asyncpg.Record:
    if not values:
        sql = INSERT_DEFAULTS.format(table=quote_ident(table), returning=_column_list(returning))
        return await conn.fetchrow(sql)
    params = _Params()
    placeholders = COMMA_JOIN.join(PARAM.format(n=params.add(v)) for v in values.values())
    sql = INSERT_ROW.format(
        table=quote_ident(table),
        columns=_column_list(list(values)),
        values=placeholders,
        returning=_column_list(returning),
    )
    return await conn.fetchrow(sql, *params.values)


async def update_row(
    conn: asyncpg.Connection,
    *,
    table: str,
    values: Mapping[str, Any],
    touch_columns: Sequence[str],
    key: Mapping[str, Any],
    returning: Sequence[str],
) -> asyncpg.Record | None:
    params = _Params()
    assignments = [
        EQUALS_PARAM.format(column=quote_ident(col), n=params.add(val))
        for col, val in values.items()
    ]
    assignments += [SET_NOW.format(column=quote_ident(col)) for col in touch_columns]
    sql = UPDATE_ROW.format(
        table=quote_ident(table),
        assignments=COMMA_JOIN.join(assignments),
        key=_key_clause(key, params),
        returning=_column_list(returning),
    )
    return await conn.fetchrow(sql, *params.values)


async def soft_delete_row(
    conn: asyncpg.Connection,
    *,
    table: str,
    flag_column: str,
    touch_columns: Sequence[str],
    key: Mapping[str, Any],
) -> bool:
    params = _Params()
    assignments = [SET_FALSE.format(column=quote_ident(flag_column))]
    assignments += [SET_NOW.format(column=quote_ident(col)) for col in touch_columns]
    sql = UPDATE_ROW.format(
        table=quote_ident(table),
        assignments=COMMA_JOIN.join(assignments),
        key=_key_clause(key, params),
        returning=quote_ident(flag_column),
    )
    return await conn.fetchrow(sql, *params.values) is not None


async def delete_row(conn: asyncpg.Connection, *, table: str, key: Mapping[str, Any]) -> bool:
    params = _Params()
    sql = DELETE_ROW.format(table=quote_ident(table), key=_key_clause(key, params))
    return await conn.fetchrow(sql, *params.values) is not None


async def metrics_scalars(
    conn: asyncpg.Connection,
    *,
    open_ticket_status: str,
    pending_withdrawal_statuses: Sequence[str],
    paid_withdrawal_status: str,
    paid_invoice_status: str,
    succeeded_payment_status: str,
) -> asyncpg.Record:
    return await conn.fetchrow(
        METRICS_SCALARS,
        open_ticket_status,
        list(pending_withdrawal_statuses),
        paid_withdrawal_status,
        paid_invoice_status,
        succeeded_payment_status,
    )


async def workers_by_verification(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(WORKERS_BY_VERIFICATION)


async def businesses_by_verification(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(BUSINESSES_BY_VERIFICATION)


async def shifts_by_status(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(SHIFTS_BY_STATUS)


async def insert_audit(
    conn: asyncpg.Connection,
    *,
    resource: str,
    record_id: str,
    action: str,
    actor_user_id: Any,
    old_values: str | None,
    new_values: str | None,
) -> None:
    await conn.execute(
        INSERT_AUDIT, resource, record_id, action, actor_user_id, old_values, new_values
    )
