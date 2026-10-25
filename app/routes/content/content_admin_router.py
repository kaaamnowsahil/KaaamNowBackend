"""Admin-only CRUD for FAQ & Help entries and Terms & Conditions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.constants.content.content_route_strings import (
    ADMIN_CONTENT_ROUTE_PREFIX,
    OPENAPI_TAG_ADMIN_CONTENT,
    PATH_FAQ_ID,
    PATH_FAQS,
    PATH_TERMS,
    PATH_TERMS_AUDIENCE,
)
from app.dependencies import RequireVerificationRead, RequireVerificationWrite
from app.schemas.content.content_schemas import (
    AdminFaq,
    AdminFaqCreate,
    AdminFaqUpdate,
    AdminTerms,
    AdminTermsUpsert,
    ContentAudience,
)
from app.services.content import content_admin_service

router = APIRouter(prefix=ADMIN_CONTENT_ROUTE_PREFIX, tags=[OPENAPI_TAG_ADMIN_CONTENT])


@router.get(
    PATH_FAQS,
    response_model=list[AdminFaq],
    summary=swagger_summary("List FAQs", SWAGGER_ROLE_ADMIN),
)
async def list_faqs(
    _: RequireVerificationRead,
    audience: ContentAudience | None = None,
    include_inactive: bool = Query(default=True),
) -> list[AdminFaq]:
    return await content_admin_service.list_faqs(audience, include_inactive)


@router.post(
    PATH_FAQS,
    response_model=AdminFaq,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Create FAQ", SWAGGER_ROLE_ADMIN),
)
async def create_faq(body: AdminFaqCreate, _: RequireVerificationWrite) -> AdminFaq:
    return await content_admin_service.create_faq(body)


@router.patch(
    PATH_FAQ_ID,
    response_model=AdminFaq,
    summary=swagger_summary("Update FAQ", SWAGGER_ROLE_ADMIN),
)
async def update_faq(faq_id: UUID, body: AdminFaqUpdate, _: RequireVerificationWrite) -> AdminFaq:
    return await content_admin_service.update_faq(faq_id, body)


@router.delete(
    PATH_FAQ_ID,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Delete FAQ", SWAGGER_ROLE_ADMIN),
)
async def delete_faq(faq_id: UUID, _: RequireVerificationWrite) -> Response:
    await content_admin_service.delete_faq(faq_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    PATH_TERMS,
    response_model=list[AdminTerms],
    summary=swagger_summary("List Terms & Conditions per audience", SWAGGER_ROLE_ADMIN),
)
async def list_terms(_: RequireVerificationRead) -> list[AdminTerms]:
    return await content_admin_service.list_terms()


@router.put(
    PATH_TERMS_AUDIENCE,
    response_model=AdminTerms,
    summary=swagger_summary("Create or replace Terms & Conditions", SWAGGER_ROLE_ADMIN),
)
async def upsert_terms(
    audience: ContentAudience, body: AdminTermsUpsert, _: RequireVerificationWrite
) -> AdminTerms:
    return await content_admin_service.upsert_terms(audience, body)


@router.delete(
    PATH_TERMS_AUDIENCE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Delete Terms & Conditions", SWAGGER_ROLE_ADMIN),
)
async def delete_terms(audience: ContentAudience, _: RequireVerificationWrite) -> Response:
    await content_admin_service.delete_terms(audience)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
