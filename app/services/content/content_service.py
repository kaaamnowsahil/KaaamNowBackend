"""Terms, FAQ & Help and support tickets."""

from __future__ import annotations

from app.config.settings import load_settings
from app.constants.content.content_route_strings import (
    MSG_CONTENT_NOT_FOUND,
    MSG_SUPPORT_SHIFT_NOT_FOUND,
    SLUG_TERMS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import not_found
from app.repositories.content import content_repository
from app.schemas.content.content_schemas import (
    ContentPage,
    FaqItem,
    FaqList,
    SupportTicketCreate,
    SupportTicketResponse,
)
from app.security.authenticated_user import AuthenticatedUser


async def get_terms(audience: str) -> ContentPage:
    async with get_pool().acquire() as conn:
        row = await content_repository.get_content_page(conn, SLUG_TERMS, audience)
    if row is None:
        raise not_found("content_not_found", MSG_CONTENT_NOT_FOUND)
    return ContentPage.model_validate(dict(row))


async def list_faqs(audience: str, search: str | None) -> FaqList:
    query = (search or "").strip() or None
    async with get_pool().acquire() as conn:
        rows = await content_repository.list_faqs(conn, audience, query)
    return FaqList(
        items=[FaqItem.model_validate(dict(r)) for r in rows],
        support_email=load_settings().support_email,
    )


async def create_ticket(
    user: AuthenticatedUser, body: SupportTicketCreate
) -> SupportTicketResponse:
    async with get_pool().acquire() as conn:
        if body.shift_id is not None and not await content_repository.user_can_see_shift(
            conn, body.shift_id, user.user_id
        ):
            raise not_found("shift_not_found", MSG_SUPPORT_SHIFT_NOT_FOUND)
        row = await content_repository.insert_support_ticket(
            conn,
            user_id=user.user_id,
            topic=body.topic,
            subject=body.subject.strip(),
            message=body.message.strip(),
            shift_id=body.shift_id,
        )
    return SupportTicketResponse(**dict(row), support_email=load_settings().support_email)
