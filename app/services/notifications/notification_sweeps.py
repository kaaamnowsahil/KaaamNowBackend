"""Push outbox delivery (background sweep job)."""

from __future__ import annotations

import asyncpg

from app.constants.notifications.notification_route_strings import PUSH_BATCH_SIZE
from app.repositories.notifications import notification_repository
from app.repositories.users import user_repository
from app.services.notifications.sources.push_sender_factory import get_push_sender
from app.utils.clock import utc_now


async def deliver_pending_pushes(pool: asyncpg.Pool) -> int:
    sender = get_push_sender()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await notification_repository.claim_pending_pushes(conn, PUSH_BATCH_SIZE)
            sent, skipped, failed = [], [], []
            for row in rows:
                devices = await user_repository.list_active_push_tokens(conn, row["user_id"])
                if not devices:
                    skipped.append(row["id"])
                    continue
                ok = await sender.send(
                    [d["push_token"] for d in devices],
                    title=row["title"],
                    body=row["body"],
                    data=dict(row["data"] or {}),
                )
                (sent if ok else failed).append(row["id"])
            now = utc_now()
            await notification_repository.set_push_status(conn, sent, "sent", now)
            await notification_repository.set_push_status(conn, skipped, "skipped", now)
            await notification_repository.set_push_status(conn, failed, "failed", now)
    return len(sent)
