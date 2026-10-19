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
SELECT id, question, answer
FROM faq_entries
WHERE is_active AND audience IN ($1, 'all')
  AND ($2::text IS NULL
       OR question ILIKE '%' || $2 || '%' OR answer ILIKE '%' || $2 || '%')
ORDER BY sort_order, question
"""

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
