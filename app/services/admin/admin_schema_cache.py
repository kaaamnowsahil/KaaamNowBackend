"""Live column metadata for registered admin resources (cached, short TTL).

A resource is only exposed when its table exists, and only columns that exist in
``information_schema`` are ever read or written.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

from app.constants.admin.admin_route_strings import (
    COLUMN_CREATED_AT,
    COLUMN_IS_ACTIVE,
    COLUMN_UPDATED_AT,
    DELETE_MODE_HARD,
    DELETE_MODE_SOFT,
    GLOBAL_HIDDEN_COLUMNS,
    GLOBAL_READ_ONLY_COLUMNS,
    OP_DELETE,
    SCHEMA_CACHE_TTL_SECONDS,
    SORT_DESC_PREFIX,
)
from app.db.pool import get_pool
from app.repositories.admin import admin_repository
from app.services.admin.admin_resources import (
    ADMIN_RESOURCES,
    AdminResource,
    find_resource,
    registered_tables,
)

_NON_SCALAR_TYPES: Final[frozenset[str]] = frozenset({"json", "jsonb", "ARRAY", "bytea"})
_TEXT_TYPES: Final[frozenset[str]] = frozenset({"character varying", "text", "character"})


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    data_type: str
    udt_name: str
    nullable: bool
    has_default: bool
    generated: bool
    max_length: int | None

    @property
    def scalar(self) -> bool:
        return self.data_type not in _NON_SCALAR_TYPES

    @property
    def textual(self) -> bool:
        return self.data_type in _TEXT_TYPES


@dataclass(frozen=True, slots=True)
class ResolvedResource:
    """A registry entry joined with the table's live columns."""

    resource: AdminResource
    columns: dict[str, ColumnInfo]

    @property
    def name(self) -> str:
        return self.resource.name

    @property
    def table(self) -> str:
        return self.resource.table

    @property
    def primary_key(self) -> tuple[str, ...]:
        return self.resource.primary_key

    @property
    def visible(self) -> list[str]:
        hidden = GLOBAL_HIDDEN_COLUMNS | self.resource.hidden
        return [c for c in self.columns if c not in hidden]

    def is_read_only(self, column: str) -> bool:
        info = self.columns[column]
        if info.generated or column in self.resource.read_only:
            return True
        if column in self.primary_key:
            # Natural / composite keys are supplied by the caller; surrogate ids are not.
            return info.has_default
        return column in GLOBAL_READ_ONLY_COLUMNS

    @property
    def writable_on_create(self) -> frozenset[str]:
        return frozenset(c for c in self.visible if not self.is_read_only(c))

    @property
    def writable_on_update(self) -> frozenset[str]:
        return frozenset(c for c in self.writable_on_create if c not in self.primary_key)

    @property
    def searchable(self) -> list[str]:
        return [c for c in self.resource.searchable if c in self.visible]

    def _scalar_subset(self, declared: tuple[str, ...] | None) -> list[str]:
        scalar = [c for c in self.visible if self.columns[c].scalar]
        return scalar if declared is None else [c for c in declared if c in scalar]

    @property
    def filterable(self) -> list[str]:
        return self._scalar_subset(self.resource.filterable)

    @property
    def sortable(self) -> list[str]:
        return self._scalar_subset(self.resource.sortable)

    @property
    def touch_columns(self) -> list[str]:
        return [COLUMN_UPDATED_AT] if COLUMN_UPDATED_AT in self.columns else []

    @property
    def delete_mode(self) -> str | None:
        if OP_DELETE not in self.resource.operations:
            return None
        if self.resource.soft_delete and COLUMN_IS_ACTIVE in self.columns:
            return DELETE_MODE_SOFT
        return DELETE_MODE_HARD

    @property
    def default_sort(self) -> str:
        declared = self.resource.default_sort
        if declared and declared.removeprefix(SORT_DESC_PREFIX) in self.columns:
            return declared
        if COLUMN_CREATED_AT in self.columns:
            return f"{SORT_DESC_PREFIX}{COLUMN_CREATED_AT}"
        return self.primary_key[0]


_cache: dict[str, dict[str, ColumnInfo]] = {}
_loaded_at: float = 0.0


async def _refresh() -> None:
    global _cache, _loaded_at
    async with get_pool().acquire() as conn:
        rows = await admin_repository.fetch_table_columns(conn, registered_tables())
    fresh: dict[str, dict[str, ColumnInfo]] = {}
    for r in rows:
        fresh.setdefault(r["table_name"], {})[r["column_name"]] = ColumnInfo(
            name=r["column_name"],
            data_type=r["data_type"],
            udt_name=r["udt_name"],
            nullable=r["is_nullable"],
            has_default=r["has_default"],
            generated=r["is_generated"],
            max_length=r["max_length"],
        )
    _cache, _loaded_at = fresh, time.monotonic()


async def _tables() -> dict[str, dict[str, ColumnInfo]]:
    if not _cache or time.monotonic() - _loaded_at > SCHEMA_CACHE_TTL_SECONDS:
        await _refresh()
    return _cache


def invalidate_schema_cache() -> None:
    global _loaded_at
    _loaded_at = 0.0


async def resolve(name: str) -> ResolvedResource | None:
    resource = find_resource(name)
    if resource is None:
        return None
    columns = (await _tables()).get(resource.table)
    if not columns or any(pk not in columns for pk in resource.primary_key):
        return None
    return ResolvedResource(resource=resource, columns=columns)


async def resolve_all() -> list[ResolvedResource]:
    tables = await _tables()
    return [
        ResolvedResource(resource=r, columns=tables[r.table])
        for r in ADMIN_RESOURCES
        if r.table in tables and all(pk in tables[r.table] for pk in r.primary_key)
    ]
