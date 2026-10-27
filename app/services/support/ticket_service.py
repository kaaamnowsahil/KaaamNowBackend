"""Admin support-ticket workflow: open → in_progress → closed.

The server decides when a ticket was closed and records which admin closed it; repeating a
request for the state a ticket is already in returns it unchanged.
"""

from __future__ import annotations

import json
from uuid import UUID

from app.constants.support.support_route_strings import (
    MSG_TICKET_ALREADY_CLOSED,
    MSG_TICKET_NOT_FOUND,
    SUPPORT_TICKET_RESOURCE,
    TICKET_STATUS_CLOSED,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.repositories.admin import admin_repository
from app.repositories.support import ticket_repository
from app.schemas.support.support_schemas import SupportTicketStatusUpdate, SupportTicketView
from app.security.authenticated_user import AuthenticatedUser


def _audit_values(row: object) -> str:
    data = dict(row)  # type: ignore[call-overload]
    return json.dumps(
        {
            "status": data["status"],
            "resolution_note": data["resolution_note"],
            "resolved_by_user_id": str(data["resolved_by_user_id"] or "") or None,
            "resolved_at": data["resolved_at"].isoformat() if data["resolved_at"] else None,
        }
    )


async def update_status(
    admin: AuthenticatedUser, ticket_id: UUID, body: SupportTicketStatusUpdate
) -> SupportTicketView:
    note = body.resolution_note.strip() if body.resolution_note else None
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            current = await ticket_repository.lock(conn, ticket_id)
            if current is None:
                raise not_found("support_ticket_not_found", MSG_TICKET_NOT_FOUND)
            if current["status"] == body.status:
                return SupportTicketView.model_validate(dict(current))
            if current["status"] == TICKET_STATUS_CLOSED:
                raise conflict("support_ticket_closed", MSG_TICKET_ALREADY_CLOSED)
            if body.status == TICKET_STATUS_CLOSED:
                updated = await ticket_repository.close(conn, ticket_id, admin.user_id, note)
            else:
                updated = await ticket_repository.start(conn, ticket_id)
            await admin_repository.insert_audit(
                conn,
                resource=SUPPORT_TICKET_RESOURCE,
                record_id=str(ticket_id),
                action="update",
                actor_user_id=admin.user_id,
                old_values=_audit_values(current),
                new_values=_audit_values(updated),
            )
    return SupportTicketView.model_validate(dict(updated))
