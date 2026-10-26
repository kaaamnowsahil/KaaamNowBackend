"""Terms, FAQ & Help and support tickets."""

from __future__ import annotations

import re

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_BUSINESS, ROLE_WORKER
from app.constants.content.content_route_strings import (
    MSG_CONTENT_NOT_FOUND,
    MSG_SUPPORT_SHIFT_NOT_FOUND,
    PRIORITY_URGENT,
    SLUG_TERMS,
    TOPIC_EMERGENCY,
)
from app.constants.notifications.notification_route_strings import KIND_SUPPORT_EMERGENCY
from app.db.pool import get_pool
from app.exceptions.api_errors import not_found
from app.repositories.content import content_repository
from app.schemas.content.content_schemas import (
    ContentPage,
    ContentSection,
    EmergencyTicketCreate,
    FaqItem,
    FaqList,
    SupportTicketCreate,
    SupportTicketResponse,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.notifications.notification_service import notify_many
from app.services.shifts.assignment_service import PARTY_BUSINESS, load_context

_SECTION_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def support_emails() -> list[str]:
    return [e.strip() for e in load_settings().support_email.split(",") if e.strip()]


def resolve_audience(audience: str | None, user: AuthenticatedUser | None) -> str:
    """Explicit query wins; otherwise a business-only account sees business copy."""
    if audience is not None:
        return audience
    if user is not None and user.has_role(ROLE_BUSINESS) and not user.has_role(ROLE_WORKER):
        return ROLE_BUSINESS
    return ROLE_WORKER


def split_sections(body_markdown: str) -> list[ContentSection]:
    headings = list(_SECTION_HEADING.finditer(body_markdown))
    sections = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body_markdown)
        title = match.group(1).strip()
        section_id = _NON_SLUG_CHARS.sub("-", title.lower()).strip("-")
        body = body_markdown[match.end() : end].strip()
        sections.append(ContentSection(id=section_id, title=title, body=body))
    return sections


async def get_terms(audience: str) -> ContentPage:
    async with get_pool().acquire() as conn:
        row = await content_repository.get_content_page(conn, SLUG_TERMS, audience)
    if row is None:
        raise not_found("content_not_found", MSG_CONTENT_NOT_FOUND)
    data = dict(row)
    return ContentPage(**data, sections=split_sections(data["body_markdown"]))


async def list_faqs(audience: str, search: str | None) -> FaqList:
    query = (search or "").strip() or None
    async with get_pool().acquire() as conn:
        rows = await content_repository.list_faqs(conn, audience, query)
    return FaqList(
        items=[FaqItem.model_validate(dict(r)) for r in rows],
        support_email=load_settings().support_email,
        support_emails=support_emails(),
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
    return SupportTicketResponse(
        **dict(row), support_email=load_settings().support_email, support_emails=support_emails()
    )


async def create_emergency(
    user: AuthenticatedUser, body: EmergencyTicketCreate
) -> SupportTicketResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, body.assignment_id, user)
            who = "Business" if party == PARTY_BUSINESS else "Worker"
            message = body.message.strip() or f"{who} pressed the emergency button."
            row = await content_repository.insert_support_ticket(
                conn,
                user_id=user.user_id,
                topic=TOPIC_EMERGENCY,
                subject=f"Emergency: {ctx['job_title']} ({who.lower()})"[:160],
                message=message,
                shift_id=ctx["shift_id"],
                priority=PRIORITY_URGENT,
                assignment_id=body.assignment_id,
            )
            await notify_many(
                conn,
                await content_repository.list_active_admin_user_ids(conn),
                KIND_SUPPORT_EMERGENCY,
                f"Emergency: {ctx['job_title']}",
                f"{who} at {ctx['business_name']} needs help. {message}"[:300],
                {
                    "ticket_id": row["id"],
                    "shift_id": ctx["shift_id"],
                    "assignment_id": body.assignment_id,
                },
            )
    return SupportTicketResponse(
        **dict(row), support_email=load_settings().support_email, support_emails=support_emails()
    )
