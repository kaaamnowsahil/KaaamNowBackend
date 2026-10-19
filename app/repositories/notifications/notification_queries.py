"""SQL for notifications (in-app centre + push outbox)."""

from __future__ import annotations

INSERT_NOTIFICATION = """
INSERT INTO notifications (user_id, kind, title, body, data)
VALUES ($1, $2, $3, $4, $5)
RETURNING id
"""

INSERT_NOTIFICATIONS_BULK = """
INSERT INTO notifications (user_id, kind, title, body, data)
SELECT unnest($1::uuid[]), $2, $3, $4, $5
"""

LIST_NOTIFICATIONS = """
SELECT id, kind, title, body, data, read_at, created_at
FROM notifications
WHERE user_id = $1 AND ($2::boolean IS FALSE OR read_at IS NULL)
ORDER BY created_at DESC
LIMIT $3 OFFSET $4
"""

COUNT_UNREAD = "SELECT count(*) FROM notifications WHERE user_id = $1 AND read_at IS NULL"

MARK_READ = """
UPDATE notifications SET read_at = COALESCE(read_at, $3)
WHERE id = $1 AND user_id = $2
"""

MARK_ALL_READ = """
UPDATE notifications SET read_at = $2 WHERE user_id = $1 AND read_at IS NULL
"""

CLAIM_PENDING_PUSHES = """
SELECT n.id, n.user_id, n.kind, n.title, n.body, n.data
FROM notifications n
WHERE n.push_status = 'pending'
ORDER BY n.created_at
LIMIT $1
FOR UPDATE SKIP LOCKED
"""

SET_PUSH_STATUS = """
UPDATE notifications SET push_status = $2, pushed_at = $3 WHERE id = ANY($1::uuid[])
"""
