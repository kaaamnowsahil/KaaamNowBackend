"""Admin-managed worker shift filter options."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from pydantic import ValidationError

from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request, conflict, not_found
from app.repositories.lookups import shift_filter_repository
from app.schemas.lookups.shift_filter_schemas import (
    ShiftFilterOption,
    ShiftFilterOptionCreate,
    ShiftFilterOptionUpdate,
)

_EMPTY_UPDATE = "shift_filter_option_empty_update"
_NOT_FOUND = "shift_filter_option_not_found"
_SLUG_TAKEN = "shift_filter_option_slug_taken"


def _model(row: asyncpg.Record) -> ShiftFilterOption:
    return ShiftFilterOption.model_validate(dict(row))


def _not_found() -> ApiError:
    return not_found(_NOT_FOUND, "This shift filter option was not found.")


def _slug_taken() -> ApiError:
    return conflict(_SLUG_TAKEN, "An option with this filter type and slug already exists.")


async def list_options(*, include_inactive: bool) -> list[ShiftFilterOption]:
    async with get_pool().acquire() as conn:
        rows = await shift_filter_repository.list_options(
            conn, include_inactive=include_inactive
        )
    return [_model(row) for row in rows]


async def get_option(option_id: UUID, *, include_inactive: bool) -> ShiftFilterOption:
    async with get_pool().acquire() as conn:
        row = await shift_filter_repository.get_option(conn, option_id)
    if row is None or (not include_inactive and not row["is_active"]):
        raise _not_found()
    return _model(row)


async def create_option(body: ShiftFilterOptionCreate) -> ShiftFilterOption:
    values = body.model_dump()
    values["filter_type"] = body.filter_type.value
    values["slug"] = body.slug.strip()
    values["label"] = body.label.strip()
    async with get_pool().acquire() as conn:
        try:
            row = await shift_filter_repository.insert_option(conn, **values)
        except asyncpg.UniqueViolationError as exc:
            raise _slug_taken() from exc
    return _model(row)


async def update_option(
    option_id: UUID, body: ShiftFilterOptionUpdate
) -> ShiftFilterOption:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise bad_request(_EMPTY_UPDATE, "Send at least one field to update.")
    async with get_pool().acquire() as conn:
        current = await shift_filter_repository.get_option(conn, option_id)
        if current is None:
            raise _not_found()
        values = dict(current)
        values.update(changes)
        try:
            validated = ShiftFilterOptionCreate.model_validate(
                {
                    key: values[key]
                    for key in (
                        "filter_type",
                        "slug",
                        "label",
                        "min_value",
                        "max_value",
                        "sort_order",
                        "is_active",
                    )
                }
            )
            row = await shift_filter_repository.update_option(
                conn,
                option_id,
                {
                    **validated.model_dump(),
                    "filter_type": validated.filter_type.value,
                    "slug": validated.slug.strip(),
                    "label": validated.label.strip(),
                },
            )
        except asyncpg.UniqueViolationError as exc:
            raise _slug_taken() from exc
        except ValidationError as exc:
            raise bad_request(
                "shift_filter_option_invalid",
                "The option values are invalid for this filter type.",
            ) from exc
    if row is None:
        raise _not_found()
    return _model(row)


async def delete_option(option_id: UUID) -> None:
    async with get_pool().acquire() as conn:
        found = await shift_filter_repository.deactivate_option(conn, option_id)
    if not found:
        raise _not_found()
