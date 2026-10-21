"""SQL for ratings."""

from __future__ import annotations

INSERT_RATING = """
INSERT INTO ratings (
    shift_id, assignment_id, direction, rater_user_id, ratee_user_id, stars, tags, review
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (assignment_id, direction) DO NOTHING
RETURNING id, direction, stars, tags, review, created_at
"""

LIST_RATINGS_FOR_ASSIGNMENT = """
SELECT id, direction, stars, tags, review, created_at
FROM ratings WHERE assignment_id = $1
ORDER BY created_at
"""

LIST_RECENT_REVIEWS_FOR_USER = """
SELECT r.stars, r.tags, r.review, r.created_at,
       COALESCE(
           NULLIF(bp.business_name, ''), NULLIF(u.full_name, ''), 'KaaamNow user'
       ) AS rater_name
FROM ratings r
JOIN users u ON u.id = r.rater_user_id
LEFT JOIN business_profiles bp
    ON bp.user_id = r.rater_user_id AND r.direction = 'business_to_worker'
WHERE r.ratee_user_id = $1 AND r.direction = $2
ORDER BY r.created_at DESC
LIMIT $3
"""
