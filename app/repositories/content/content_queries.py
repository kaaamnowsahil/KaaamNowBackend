"""SQL for content_pages, faq_entries and support_tickets."""

from __future__ import annotations

GET_CONTENT_PAGE = """
SELECT slug, audience, title, body_markdown, effective_date, updated_at
FROM content_pages
WHERE slug = $1 AND audience IN ($2, 'all')
ORDER BY (audience = $2) DESC
LIMIT 1
"""

LIST_FAQS = """
SELECT id, slug, question, answer
FROM faq_entries
WHERE is_active AND audience IN ($1, 'all')
  AND ($2::text IS NULL
       OR question ILIKE '%' || $2 || '%' OR answer ILIKE '%' || $2 || '%')
ORDER BY sort_order, question
"""

_ADMIN_FAQ_COLUMNS = (
    "id, audience, slug, question, answer, sort_order, is_active, created_at, updated_at"
)

ADMIN_LIST_FAQS = f"""
SELECT {_ADMIN_FAQ_COLUMNS}
FROM faq_entries
WHERE ($1::varchar IS NULL OR audience = $1) AND ($2 OR is_active)
ORDER BY audience, sort_order, question
"""

ADMIN_GET_FAQ = f"SELECT {_ADMIN_FAQ_COLUMNS} FROM faq_entries WHERE id = $1"

ADMIN_INSERT_FAQ = f"""
INSERT INTO faq_entries (audience, slug, question, answer, sort_order, is_active)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING {_ADMIN_FAQ_COLUMNS}
"""

ADMIN_UPDATE_FAQ = f"""
UPDATE faq_entries SET
    audience = $2, slug = $3, question = $4, answer = $5, sort_order = $6, is_active = $7,
    updated_at = now()
WHERE id = $1
RETURNING {_ADMIN_FAQ_COLUMNS}
"""

ADMIN_DELETE_FAQ = "DELETE FROM faq_entries WHERE id = $1"

_ADMIN_TERMS_COLUMNS = "id, audience, title, body_markdown, effective_date, created_at, updated_at"

ADMIN_LIST_TERMS = f"""
SELECT {_ADMIN_TERMS_COLUMNS} FROM content_pages WHERE slug = $1 ORDER BY audience
"""

ADMIN_UPSERT_TERMS = f"""
INSERT INTO content_pages (slug, audience, title, body_markdown, effective_date)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (slug, audience) DO UPDATE SET
    title = EXCLUDED.title, body_markdown = EXCLUDED.body_markdown,
    effective_date = EXCLUDED.effective_date, updated_at = now()
RETURNING {_ADMIN_TERMS_COLUMNS}
"""

ADMIN_DELETE_TERMS = "DELETE FROM content_pages WHERE slug = $1 AND audience = $2"

USER_CAN_SEE_SHIFT = """
SELECT EXISTS (
    SELECT 1 FROM shifts s JOIN business_profiles bp ON bp.id = s.business_profile_id
    WHERE s.id = $1 AND bp.user_id = $2
) OR EXISTS (
    SELECT 1 FROM shift_assignments a JOIN worker_profiles wp ON wp.id = a.worker_profile_id
    WHERE a.shift_id = $1 AND wp.user_id = $2
)
"""

INSERT_SUPPORT_TICKET = """
INSERT INTO support_tickets (user_id, topic, subject, message, shift_id)
VALUES ($1, $2, $3, $4, $5)
RETURNING id, topic, subject, status, created_at
"""
