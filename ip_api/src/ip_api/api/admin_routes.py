"""Admin routes for the default Word template library.

Upload a template once to ``{folder_name}/{template_name}``. The default folder
is ``ipp_default_template``. Jobs can then name that template instead of
re-uploading the .docx. Storage follows ``FILE_STORAGE_BACKEND``.

Every route requires the ``X-Admin-Api-Key`` header to match ``ADMIN_API_KEY``.
When that env var is unset the whole router refuses requests.
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
    DEFAULT_TEMPLATE_FOLDER,
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
        f"/api/v1/admin/templates/{record.folder_name}/{record.template_name}/download"
    )


def _to_response(record: TemplateRecord) -> TemplateRecordResponse:
    return TemplateRecordResponse(
        **record.to_dict(), download_url=_download_url(record)
    )


def _bad_name(error: TemplateNameError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


async def _save_uploaded_template(
    *,
    folder_name: str | None,
    file: UploadFile,
    template_name: str | None,
    uploaded_by: str | None,
    store: TemplateStore,
    cfg: Settings,
) -> TemplateRecordResponse:
    """Store a Word template at ``{folder_name}/{template_name}``."""
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
            folder_name=folder_name,
            template_name=template_name or file.filename or "",
            content=content,
            uploaded_by=uploaded_by,
        )
    except TemplateNameError as error:
        raise _bad_name(error) from error
    return _to_response(record)


def _list_for_folder(
    folder_name: str | None,
    limit: int,
    store: TemplateStore,
) -> TemplateListResponse:
    try:
        records = store.list(folder_name=folder_name, limit=limit)
    except TemplateNameError as error:
        raise _bad_name(error) from error
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
    file: UploadFile = File(..., description="Word .docx template"),
    folder_name: str = Form(
        default=DEFAULT_TEMPLATE_FOLDER,
        description="Library folder. Default: ipp_default_template.",
    ),
    template_name: str | None = Form(
        default=None,
        description="Stored name; defaults to the uploaded filename. '.docx' is enforced.",
    ),
    uploaded_by: str | None = Form(default=None),
) -> TemplateRecordResponse:
    """Store a Word template at ``{folder_name}/{template_name}`` (re-upload replaces)."""
    return await _save_uploaded_template(
        folder_name=folder_name,
        file=file,
        template_name=template_name,
        uploaded_by=uploaded_by,
        store=store,
        cfg=cfg,
    )


@router.post(
    "/templates/{folder_name}",
    response_model=TemplateRecordResponse,
    status_code=201,
    dependencies=[Depends(require_admin_key)],
)
async def upload_folder_template(
    folder_name: str,
    store: TemplateStoreDep,
    cfg: SettingsDep,
    file: UploadFile = File(..., description="Word .docx template"),
    template_name: str | None = Form(
        default=None,
        description="Stored name; defaults to the uploaded filename. '.docx' is enforced.",
    ),
    uploaded_by: str | None = Form(default=None),
) -> TemplateRecordResponse:
    """Upload into a library folder, e.g. ``/templates/ipp_default_template``."""
    return await _save_uploaded_template(
        folder_name=folder_name,
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
    folder_name: str | None = Query(
        default=None,
        description="Filter to one folder (default library is ipp_default_template).",
    ),
    limit: int = Query(default=200, ge=1, le=500),
) -> TemplateListResponse:
    return _list_for_folder(folder_name, limit, store)


@router.get(
    "/templates/folders",
    response_model=list[str],
    dependencies=[Depends(require_admin_key)],
)
def list_template_folders(store: TemplateStoreDep) -> list[str]:
    return store.list_folders()


@router.get(
    "/templates/{folder_name}",
    response_model=TemplateListResponse,
    dependencies=[Depends(require_admin_key)],
)
def list_folder_templates(
    folder_name: str,
    store: TemplateStoreDep,
    limit: int = Query(default=200, ge=1, le=500),
) -> TemplateListResponse:
    """List templates in one library folder."""
    return _list_for_folder(folder_name, limit, store)


@router.get(
    "/templates/{folder_name}/{template_name}",
    response_model=TemplateRecordResponse,
    dependencies=[Depends(require_admin_key)],
)
def get_template(
    folder_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> TemplateRecordResponse:
    try:
        record = store.get(folder_name, template_name)
    except TemplateNameError as error:
        raise _bad_name(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _to_response(record)


@router.get(
    "/templates/{folder_name}/{template_name}/download",
    dependencies=[Depends(require_admin_key)],
)
def download_template(
    folder_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> Response:
    """Return the stored .docx bytes, from local disk or Azure Blob."""
    try:
        record = store.get(folder_name, template_name)
        content = store.read_bytes(record)
    except TemplateNameError as error:
        raise _bad_name(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    return Response(
        content=content,
        media_type=TEMPLATE_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{record.template_name}"',
        },
    )


@router.delete(
    "/templates/{folder_name}/{template_name}",
    response_model=TemplateDeletedResponse,
    dependencies=[Depends(require_admin_key)],
)
def delete_template(
    folder_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> TemplateDeletedResponse:
    try:
        record = store.delete(folder_name, template_name)
    except TemplateNameError as error:
        raise _bad_name(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return TemplateDeletedResponse(
        folder_name=record.folder_name,
        template_name=record.template_name,
        location=record.location,
    )
