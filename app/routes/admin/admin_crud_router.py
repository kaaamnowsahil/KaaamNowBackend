"""Admin dashboard: generic list / read / create / update / delete / export + metrics.

Static paths (``/resources``, ``/metrics/overview``, ``/{resource}/export.csv``) are declared
before the parameterised ones so they win route matching.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request, Response, status

from app.constants.admin.admin_route_strings import (
    ADMIN_CRUD_ROUTE_PREFIX,
    DESC_LIST_RESOURCE,
    EXPORT_CONTENT_DISPOSITION,
    EXPORT_MEDIA_TYPE,
    HEADER_CONTENT_DISPOSITION,
    OPENAPI_TAG_ADMIN_DATA,
    PATH_ADMIN_METRICS_OVERVIEW,
    PATH_ADMIN_RECORD,
    PATH_ADMIN_RESOURCE,
    PATH_ADMIN_RESOURCE_EXPORT,
    PATH_ADMIN_RESOURCES,
    RESERVED_LIST_PARAMS,
    SEARCH_MAX_LENGTH,
)
from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.dependencies import RequireVerificationRead, RequireVerificationWrite
from app.schemas.admin.admin_schemas import (
    AdminMetricsOverview,
    AdminRecord,
    AdminRecordPage,
    AdminResourceList,
)
from app.services.admin import admin_crud_service, admin_metrics_service

router = APIRouter(prefix=ADMIN_CRUD_ROUTE_PREFIX, tags=[OPENAPI_TAG_ADMIN_DATA])

RecordBody = Annotated[dict[str, Any], Body()]


def _field_filters(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items() if k not in RESERVED_LIST_PARAMS}


@router.get(
    PATH_ADMIN_RESOURCES,
    response_model=AdminResourceList,
    summary=swagger_summary("Admin resources & columns", SWAGGER_ROLE_ADMIN),
)
async def list_resources(_: RequireVerificationRead) -> AdminResourceList:
    return await admin_crud_service.list_resources()


@router.get(
    PATH_ADMIN_METRICS_OVERVIEW,
    response_model=AdminMetricsOverview,
    summary=swagger_summary("Dashboard overview metrics", SWAGGER_ROLE_ADMIN),
)
async def metrics_overview(_: RequireVerificationRead) -> AdminMetricsOverview:
    return await admin_metrics_service.overview()


@router.get(
    PATH_ADMIN_RESOURCE_EXPORT,
    response_class=Response,
    summary=swagger_summary("Export filtered list as CSV", SWAGGER_ROLE_ADMIN),
    description=DESC_LIST_RESOURCE,
)
async def export_records(
    resource: str,
    request: Request,
    _: RequireVerificationRead,
    q: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    sort: str | None = Query(default=None),
) -> Response:
    name, content = await admin_crud_service.export_csv(
        resource, q=q, sort=sort, raw_filters=_field_filters(request)
    )
    return Response(
        content=content,
        media_type=EXPORT_MEDIA_TYPE,
        headers={HEADER_CONTENT_DISPOSITION: EXPORT_CONTENT_DISPOSITION.format(name=name)},
    )


@router.get(
    PATH_ADMIN_RESOURCE,
    response_model=AdminRecordPage,
    summary=swagger_summary("List / search / filter records", SWAGGER_ROLE_ADMIN),
    description=DESC_LIST_RESOURCE,
)
async def list_records(
    resource: str,
    request: Request,
    _: RequireVerificationRead,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    sort: str | None = Query(default=None),
) -> AdminRecordPage:
    return await admin_crud_service.list_records(
        resource,
        limit=limit,
        offset=offset,
        q=q,
        sort=sort,
        raw_filters=_field_filters(request),
    )


@router.post(
    PATH_ADMIN_RESOURCE,
    response_model=AdminRecord,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Create record", SWAGGER_ROLE_ADMIN),
)
async def create_record(
    resource: str, body: RecordBody, _: RequireVerificationWrite
) -> AdminRecord:
    return await admin_crud_service.create_record(resource, body)


@router.get(
    PATH_ADMIN_RECORD,
    response_model=AdminRecord,
    summary=swagger_summary("Get record", SWAGGER_ROLE_ADMIN),
)
async def get_record(resource: str, record_id: str, _: RequireVerificationRead) -> AdminRecord:
    return await admin_crud_service.get_record(resource, record_id)


@router.patch(
    PATH_ADMIN_RECORD,
    response_model=AdminRecord,
    summary=swagger_summary("Update record (partial)", SWAGGER_ROLE_ADMIN),
)
async def update_record(
    resource: str, record_id: str, body: RecordBody, _: RequireVerificationWrite
) -> AdminRecord:
    return await admin_crud_service.update_record(resource, record_id, body)


@router.delete(
    PATH_ADMIN_RECORD,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Delete record (soft or hard per resource)", SWAGGER_ROLE_ADMIN),
)
async def delete_record(resource: str, record_id: str, _: RequireVerificationWrite) -> Response:
    await admin_crud_service.delete_record(resource, record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
