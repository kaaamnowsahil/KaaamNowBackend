"""SQL for worker shift filter options."""

from __future__ import annotations

_COLUMNS = """
id, filter_type, slug, label, min_value, max_value, sort_order, is_active,
created_at, updated_at
"""

LIST_OPTIONS = f"""
SELECT {_COLUMNS}
FROM shift_filter_options
WHERE ($1::boolean OR is_active)
ORDER BY filter_type, sort_order, label
"""

GET_OPTION = f"SELECT {_COLUMNS} FROM shift_filter_options WHERE id = $1"

INSERT_OPTION = f"""
INSERT INTO shift_filter_options
    (filter_type, slug, label, min_value, max_value, sort_order, is_active)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING {_COLUMNS}
"""

UPDATE_OPTION = f"""
UPDATE shift_filter_options SET
    filter_type = $2,
    slug = $3,
    label = $4,
    min_value = $5,
    max_value = $6,
    sort_order = $7,
    is_active = $8,
    updated_at = now()
WHERE id = $1
RETURNING {_COLUMNS}
"""

DEACTIVATE_OPTION = """
UPDATE shift_filter_options
SET is_active = false, updated_at = now()
WHERE id = $1
RETURNING id
"""
