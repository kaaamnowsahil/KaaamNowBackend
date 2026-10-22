"""SQL builders for lookup tables. ``table`` only ever comes from ``LookupResource``."""

from __future__ import annotations

from typing import Final

_COLUMNS: Final[str] = "id, slug, name, icon, sort_order, is_active, created_at, updated_at"


def list_items(table: str) -> str:
    return f"""
SELECT {_COLUMNS} FROM {table}
WHERE ($1::boolean OR is_active)
  AND ($2::text IS NULL OR slug ILIKE '%' || $2 || '%' OR name ILIKE '%' || $2 || '%')
ORDER BY sort_order, name
"""


def get_item(table: str) -> str:
    return f"SELECT {_COLUMNS} FROM {table} WHERE id = $1"


def insert_item(table: str) -> str:
    return f"""
INSERT INTO {table} (slug, name, icon, sort_order, is_active)
VALUES ($1, $2, $3, $4, $5)
RETURNING {_COLUMNS}
"""


def update_item(table: str) -> str:
    return f"""
UPDATE {table} SET
    slug       = COALESCE($2, slug),
    name       = COALESCE($3, name),
    icon       = COALESCE($4, icon),
    sort_order = COALESCE($5, sort_order),
    is_active  = COALESCE($6, is_active),
    updated_at = now()
WHERE id = $1
RETURNING {_COLUMNS}
"""


def deactivate_item(table: str) -> str:
    return f"UPDATE {table} SET is_active = false, updated_at = now() WHERE id = $1 RETURNING id"
