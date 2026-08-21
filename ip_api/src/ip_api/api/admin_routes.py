"""Admin routes for the customer template library.

Upload a Word template once to ``{customer_name}/{template_name}``, then submit
document jobs against it by name instead of re-uploading the .docx. Storage
follows ``FILE_STORAGE_BACKEND`` (local filesystem or Azure Blob).

Every route requires the ``X-Admin-Api-Key`` header to match ``ADMIN_API_KEY``.
When that env var is unset the whole router refuses requests, so an unconfigured
deployment cannot expose template writes.
"""

from __future__ import annotations

import secrets

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile

from ip_api.api.dependencies import get_settings_dependency, get_template_store_dep
from ip_api.api.schemas import (
    TemplateDeletedResponse,
    TemplateListResponse,
    TemplateRecordResponse,
)
from ip_api.core.settings import Settings
from ip_api.storage.template_store import (
    TEMPLATE_CONTENT_TYPE,
    TEMPLATE_SUFFIX,
    TemplateNameError,
    TemplateRecord,
    TemplateStore,
)

ADMIN_KEY_HEADER = "X-Admin-Api-Key"

router = APIRouter(prefix="/admin", tags=["admin"])

TemplateStoreDep = Annotated[TemplateStore, Depends(get_template_store_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings_dependency)]


def require_admin_key(
    cfg: SettingsDep,
    x_admin_api_key: str | None = Header(default=None, alias=ADMIN_KEY_HEADER),
) -> None:
    configured = cfg.admin_api_key
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="Admin API is disabled. Set ADMIN_API_KEY to enable template management.",
        )
    if not x_admin_api_key or not secrets.compare_digest(x_admin_api_key, configured):
        raise HTTPException(status_code=401, detail=f"Missing or invalid {ADMIN_KEY_HEADER}")


def _max_bytes(cfg: Settings) -> int:
    return cfg.max_upload_mb * 1024 * 1024


def _download_url(record: TemplateRecord) -> str:
    return (
        f"/api/v1/admin/templates/{record.customer_name}/{record.template_name}/download"
    )


def _to_response(record: TemplateRecord) -> TemplateRecordResponse:
    return TemplateRecordResponse(
        **record.to_dict(), download_url=_download_url(record)
    )


def _bad_name(exc: TemplateNameError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _save_uploaded_template(
    *,
    customer_name: str,
    file: UploadFile,
    template_name: str | None,
    uploaded_by: str | None,
    store: TemplateStore,
    cfg: Settings,
) -> TemplateRecordResponse:
    """Store a Word template at ``{customer_name}/{template_name}`` (local disk or blob)."""
    if not (file.filename or "").lower().endswith(TEMPLATE_SUFFIX):
        raise HTTPException(
            status_code=400,
            detail=f"Only Word templates are accepted (expected a '{TEMPLATE_SUFFIX}' file)",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded template is empty")
    if len(content) > _max_bytes(cfg):
        raise HTTPException(
            status_code=413, detail=f"File too large. Max {cfg.max_upload_mb} MB"
        )

    try:
        record = store.save(
            customer_name=customer_name,
            template_name=template_name or file.filename or "",
            content=content,
            uploaded_by=uploaded_by,
        )
    except TemplateNameError as exc:
        raise _bad_name(exc) from exc
    return _to_response(record)


def _list_for_customer(
    customer_name: str | None,
    limit: int,
    store: TemplateStore,
) -> TemplateListResponse:
    try:
        records = store.list(customer_name=customer_name, limit=limit)
    except TemplateNameError as exc:
        raise _bad_name(exc) from exc
    return TemplateListResponse(
        count=len(records),
        storage_backend=store.backend,
        templates=[_to_response(record) for record in records],
    )


@router.post(
    "/templates",
    response_model=TemplateRecordResponse,
    status_code=201,
    dependencies=[Depends(require_admin_key)],
)
async def upload_template(
    store: TemplateStoreDep,
    cfg: SettingsDep,
    customer_name: str = Form(..., description="Customer folder, e.g. acme-corp"),
    file: UploadFile = File(..., description="Word .docx template"),
    template_name: str | None = Form(
        default=None,
        description="Stored name; defaults to the uploaded filename. '.docx' is enforced.",
    ),
    uploaded_by: str | None = Form(default=None),
) -> TemplateRecordResponse:
    """Store a Word template at ``{customer_name}/{template_name}`` (re-upload replaces)."""
    return await _save_uploaded_template(
        customer_name=customer_name,
        file=file,
        template_name=template_name,
        uploaded_by=uploaded_by,
        store=store,
        cfg=cfg,
    )


@router.post(
    "/templates/{customer_name}",
    response_model=TemplateRecordResponse,
    status_code=201,
    dependencies=[Depends(require_admin_key)],
)
async def upload_customer_template(
    customer_name: str,
    store: TemplateStoreDep,
    cfg: SettingsDep,
    file: UploadFile = File(..., description="Word .docx template"),
    template_name: str | None = Form(
        default=None,
        description="Stored name; defaults to the uploaded filename. '.docx' is enforced.",
    ),
    uploaded_by: str | None = Form(default=None),
) -> TemplateRecordResponse:
    """Dedicated customer-folder upload: ``templates/{customer_name}/{template_name}``."""
    return await _save_uploaded_template(
        customer_name=customer_name,
        file=file,
        template_name=template_name,
        uploaded_by=uploaded_by,
        store=store,
        cfg=cfg,
    )


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    dependencies=[Depends(require_admin_key)],
)
def list_templates(
    store: TemplateStoreDep,
    customer_name: str | None = Query(default=None, description="Filter to one customer"),
    limit: int = Query(default=200, ge=1, le=500),
) -> TemplateListResponse:
    return _list_for_customer(customer_name, limit, store)


@router.get(
    "/templates/customers",
    response_model=list[str],
    dependencies=[Depends(require_admin_key)],
)
def list_template_customers(store: TemplateStoreDep) -> list[str]:
    return store.list_customers()


@router.get(
    "/templates/{customer_name}",
    response_model=TemplateListResponse,
    dependencies=[Depends(require_admin_key)],
)
def list_customer_templates(
    customer_name: str,
    store: TemplateStoreDep,
    limit: int = Query(default=200, ge=1, le=500),
) -> TemplateListResponse:
    """List templates stored for one customer (local disk or blob)."""
    return _list_for_customer(customer_name, limit, store)


@router.get(
    "/templates/{customer_name}/{template_name}",
    response_model=TemplateRecordResponse,
    dependencies=[Depends(require_admin_key)],
)
def get_template(
    customer_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> TemplateRecordResponse:
    try:
        record = store.get(customer_name, template_name)
    except TemplateNameError as exc:
        raise _bad_name(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(record)


@router.get(
    "/templates/{customer_name}/{template_name}/download",
    dependencies=[Depends(require_admin_key)],
)
def download_template(
    customer_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> Response:
    """Return the stored .docx bytes, from local disk or Azure Blob."""
    try:
        record = store.get(customer_name, template_name)
        content = store.read_bytes(record)
    except TemplateNameError as exc:
        raise _bad_name(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=TEMPLATE_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{record.template_name}"',
        },
    )


@router.delete(
    "/templates/{customer_name}/{template_name}",
    response_model=TemplateDeletedResponse,
    dependencies=[Depends(require_admin_key)],
)
def delete_template(
    customer_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> TemplateDeletedResponse:
    try:
        record = store.delete(customer_name, template_name)
    except TemplateNameError as exc:
        raise _bad_name(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TemplateDeletedResponse(
        customer_name=record.customer_name,
        template_name=record.template_name,
        location=record.location,
    )
