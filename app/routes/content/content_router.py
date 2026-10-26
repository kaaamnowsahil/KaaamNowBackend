"""Public content (terms, FAQ) and signed-in support tickets."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.constants.application.application_common import (
    SWAGGER_ROLE_ANY_USER,
    SWAGGER_ROLE_PARTICIPANT,
    SWAGGER_ROLE_PUBLIC,
    swagger_summary,
)
from app.constants.content.content_route_strings import (
    CONTENT_ROUTE_PREFIX,
    FAQ_SEARCH_MAX_LENGTH,
    OPENAPI_TAG_CONTENT,
    OPENAPI_TAG_SUPPORT,
    PATH_EMERGENCY,
    PATH_FAQS,
    PATH_TERMS,
    PATH_TICKETS,
    SUPPORT_ROUTE_PREFIX,
)
from app.dependencies import CurrentUser, OptionalUser
from app.schemas.content.content_schemas import (
    Audience,
    ContentPage,
    EmergencyTicketCreate,
    FaqList,
    SupportTicketCreate,
    SupportTicketResponse,
)
from app.services.content import content_service

router = APIRouter(prefix=CONTENT_ROUTE_PREFIX, tags=[OPENAPI_TAG_CONTENT])
support_router = APIRouter(prefix=SUPPORT_ROUTE_PREFIX, tags=[OPENAPI_TAG_SUPPORT])


@router.get(
    PATH_TERMS,
    response_model=ContentPage,
    summary=swagger_summary("Terms & Conditions", SWAGGER_ROLE_PUBLIC),
)
async def terms(user: OptionalUser, audience: Audience | None = None) -> ContentPage:
    return await content_service.get_terms(content_service.resolve_audience(audience, user))


@router.get(
    PATH_FAQS,
    response_model=FaqList,
    summary=swagger_summary("FAQ & Help", SWAGGER_ROLE_PUBLIC),
)
async def faqs(
    user: OptionalUser,
    audience: Audience | None = None,
    q: str | None = Query(default=None, max_length=FAQ_SEARCH_MAX_LENGTH),
) -> FaqList:
    return await content_service.list_faqs(content_service.resolve_audience(audience, user), q)


@support_router.post(
    PATH_TICKETS,
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Contact support", SWAGGER_ROLE_ANY_USER),
)
async def create_ticket(body: SupportTicketCreate, user: CurrentUser) -> SupportTicketResponse:
    return await content_service.create_ticket(user, body)


@support_router.post(
    PATH_EMERGENCY,
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Emergency on a booking", SWAGGER_ROLE_PARTICIPANT),
)
async def emergency(body: EmergencyTicketCreate, user: CurrentUser) -> SupportTicketResponse:
    return await content_service.create_emergency(user, body)
