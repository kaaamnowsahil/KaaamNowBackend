"""Admin management of FAQ entries and Terms & Conditions pages."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.content.content_route_strings import (
    MSG_CONTENT_NOT_FOUND,
    MSG_FAQ_EXISTS,
    MSG_FAQ_NOT_FOUND,
    SLUG_TERMS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import conflict, not_found
from app.repositories.content import content_repository
from app.schemas.content.content_schemas import (
    AdminFaq,
    AdminFaqCreate,
    AdminFaqUpdate,
    AdminTerms,
    AdminTermsUpsert,
)


def _faq(row: asyncpg.Record) -> AdminFaq:
    return AdminFaq.model_validate(dict(row))


def _terms(row: asyncpg.Record) -> AdminTerms:
    return AdminTerms.model_validate(dict(row))


def _faq_exists() -> Exception:
    return conflict("faq_exists", MSG_FAQ_EXISTS)


async def list_faqs(audience: str | None, include_inactive: bool) -> list[AdminFaq]:
    async with get_pool().acquire() as conn:
        rows = await content_repository.admin_list_faqs(conn, audience, include_inactive)
    return [_faq(r) for r in rows]


async def create_faq(body: AdminFaqCreate) -> AdminFaq:
    values = body.model_dump()
    values["question"] = values["question"].strip()
    values["answer"] = values["answer"].strip()
    try:
        async with get_pool().acquire() as conn:
            row = await content_repository.admin_insert_faq(conn, values)
    except asyncpg.UniqueViolationError as exc:
        raise _faq_exists() from exc
    return _faq(row)


async def update_faq(faq_id: UUID, body: AdminFaqUpdate) -> AdminFaq:
    changes = body.model_dump(exclude_unset=True)
    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                current = await content_repository.admin_get_faq(conn, faq_id)
                if current is None:
                    raise not_found("faq_not_found", MSG_FAQ_NOT_FOUND)
                values = {**dict(current), **changes}
                values["question"] = values["question"].strip()
                values["answer"] = values["answer"].strip()
                row = await content_repository.admin_update_faq(conn, faq_id, values)
    except asyncpg.UniqueViolationError as exc:
        raise _faq_exists() from exc
    return _faq(row)


async def delete_faq(faq_id: UUID) -> None:
    async with get_pool().acquire() as conn:
        deleted = await content_repository.admin_delete_faq(conn, faq_id)
    if not deleted:
        raise not_found("faq_not_found", MSG_FAQ_NOT_FOUND)


async def list_terms() -> list[AdminTerms]:
    async with get_pool().acquire() as conn:
        rows = await content_repository.admin_list_pages(conn, SLUG_TERMS)
    return [_terms(r) for r in rows]


async def upsert_terms(audience: str, body: AdminTermsUpsert, slug: str = SLUG_TERMS) -> AdminTerms:
    values = body.model_dump()
    values["title"] = values["title"].strip()
    async with get_pool().acquire() as conn:
        row = await content_repository.admin_upsert_page(conn, SLUG_TERMS, audience, values)
    return _terms(row)


async def delete_terms(audience: str) -> None:
    async with get_pool().acquire() as conn:
        deleted = await content_repository.admin_delete_page(conn, SLUG_TERMS, audience)
    if not deleted:
        raise not_found("content_not_found", MSG_CONTENT_NOT_FOUND)
