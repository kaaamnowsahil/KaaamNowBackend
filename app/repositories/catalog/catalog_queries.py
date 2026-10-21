"""SQL for work_categories, languages and platform_fee_policies."""

from __future__ import annotations

LIST_WORK_CATEGORIES = """
SELECT id, slug, name, icon FROM work_categories WHERE is_active ORDER BY sort_order, name
"""

LIST_BUSINESS_TYPES = """
SELECT id, slug, name, icon FROM business_types WHERE is_active ORDER BY sort_order, name
"""

GET_BUSINESS_TYPE_BY_SLUG = """
SELECT id, slug, name FROM business_types WHERE slug = $1 AND is_active
"""

GET_CATEGORY_BY_SLUG = "SELECT id, slug, name FROM work_categories WHERE slug = $1 AND is_active"

GET_CATEGORY_IDS_BY_SLUGS = """
SELECT id, slug FROM work_categories WHERE slug = ANY($1::varchar[]) AND is_active
"""

LIST_LANGUAGES = """
SELECT code, english_name, native_name FROM languages WHERE is_active ORDER BY sort_order, code
"""

GET_ACTIVE_FEE_POLICY = """
SELECT version, percentage FROM platform_fee_policies WHERE is_active
"""
