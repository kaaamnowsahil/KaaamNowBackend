"""SQL for work_categories and platform_fee_policies."""

from __future__ import annotations

GET_BUSINESS_TYPE_BY_SLUG = """
SELECT id, slug, name FROM business_types WHERE slug = $1 AND is_active
"""

GET_BUSINESS_TYPE_IDS_BY_SLUGS = """
SELECT id, slug FROM business_types WHERE slug = ANY($1::varchar[]) AND is_active
"""

GET_CATEGORY_BY_SLUG = "SELECT id, slug, name FROM work_categories WHERE slug = $1 AND is_active"

GET_CATEGORY_IDS_BY_SLUGS = """
SELECT id, slug FROM work_categories WHERE slug = ANY($1::varchar[]) AND is_active
"""

GET_ACTIVE_FEE_POLICY = """
SELECT version, percentage, worker_percentage, gateway_percentage, tax_percentage, tax_label,
    tax_base
FROM platform_fee_policies WHERE is_active
"""

GET_SEARCH_RADIUS_SETTINGS = "SELECT * FROM search_radius_settings WHERE singleton"
