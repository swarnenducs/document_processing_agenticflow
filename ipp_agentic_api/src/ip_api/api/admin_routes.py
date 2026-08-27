"""Admin routes for the default Word template library.

Upload a template once to ``{folder_name}/{template_name}``. The default folder
is ``ipp_pricing_default_template``. On Azure Blob that is
``{AZURE_BLOB_TEMPLATE_PREFIX}/ipp_pricing_default_template/{name}.docx``.
Jobs can then name that template instead of re-uploading the .docx.
"""

from __future__ import annotations

import secrets

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile

from ip_api.api.dependencies import get_settings_dependency, get_template_store_dep
from ip_api.api.schemas import (
    MasterDataDeletedResponse,
    MasterDataListResponse,
    MasterDataRecordResponse,
    MasterDataUpdateRequest,
    MasterDataUpsertRequest,
    TemplateDeletedResponse,
    TemplateListResponse,
    TemplateRecordResponse,
)
from ip_api.core.settings import Settings
from ip_api.storage.master_data_store import MasterDataKeyError, MasterDataStore
from ip_api.storage.template_store import (
    DEFAULT_TEMPLATE_FOLDER,
    TEMPLATE_CONTENT_TYPE,
    TEMPLATE_SUFFIX,
    TemplateNameError,
    TemplateRecord,
    TemplateStore,
)

ADMIN_KEY_HEADER = "X-Admin-Api-Key"

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

TemplateStoreDep = Annotated[TemplateStore, Depends(get_template_store_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings_dependency)]


def require_admin_key(
    cfg: SettingsDep,
    x_admin_api_key: str | None = Header(
        default=None,
        alias=ADMIN_KEY_HEADER,
        description="Must match env ADMIN_API_KEY. Admin is 503 if that env is empty.",
    ),
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
        records = store.list_library(folder_name=folder_name, limit=limit)
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
    summary="Upload template (optional folder in form)",
)
async def upload_template(
    store: TemplateStoreDep,
    cfg: SettingsDep,
    file: UploadFile = File(..., description="Word .docx template"),
    folder_name: str = Form(
        default=DEFAULT_TEMPLATE_FOLDER,
        description=f"Library folder. Default: {DEFAULT_TEMPLATE_FOLDER}.",
    ),
    template_name: str | None = Form(
        default=None,
        description="Stored name; defaults to the uploaded filename. '.docx' is enforced.",
    ),
    uploaded_by: str | None = Form(default=None),
) -> TemplateRecordResponse:
    """
    Store a Word `.docx` at `{folder_name}/{template_name}`. Re-upload replaces.

    Header **`X-Admin-Api-Key`** must equal env `ADMIN_API_KEY`. Multipart: `file`,
    optional `folder_name` (default `ipp_pricing_default_template`), `template_name`,
    `uploaded_by`. On Azure Blob: `templates/ipp_pricing_default_template/{name}.docx`
    (prefix from `AZURE_BLOB_TEMPLATE_PREFIX`).
    """
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
    summary="Upload template into a folder path",
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
    """Same as POST `/templates` but folder is in the URL, e.g. `/templates/ipp_pricing_default_template`."""
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
    summary="List templates",
)
def list_templates(
    store: TemplateStoreDep,
    folder_name: str | None = Query(
        default=None,
        description=f"Filter to one folder (default library is {DEFAULT_TEMPLATE_FOLDER}).",
    ),
    limit: int = Query(default=200, ge=1, le=500),
) -> TemplateListResponse:
    """Optional `folder_name` query. Requires `X-Admin-Api-Key`."""
    return _list_for_folder(folder_name, limit, store)


@router.get(
    "/templates/folders",
    response_model=list[str],
    dependencies=[Depends(require_admin_key)],
    summary="List library folder names",
)
def list_template_folders(store: TemplateStoreDep) -> list[str]:
    """Distinct folders that contain at least one stored template."""
    return store.list_folders()


@router.get(
    "/templates/{folder_name}",
    response_model=TemplateListResponse,
    dependencies=[Depends(require_admin_key)],
    summary="List templates in one folder",
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
    summary="Get template metadata",
)
def get_template(
    folder_name: str,
    template_name: str,
    store: TemplateStoreDep,
) -> TemplateRecordResponse:
    """Metadata only (folder, name, size, storage_ref). Use `/download` for bytes."""
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
    summary="Download stored .docx",
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
    summary="Delete template (file + SQL row)",
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


def _master_store() -> MasterDataStore:
    return MasterDataStore()


def _master_http(error: MasterDataKeyError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.post(
    "/master-data",
    response_model=MasterDataRecordResponse,
    status_code=201,
    dependencies=[Depends(require_admin_key)],
    summary="Add or replace a master-data block",
)
def upsert_master_data(body: MasterDataUpsertRequest) -> MasterDataRecordResponse:
    """
    Insert or replace a SQL `master_data` row used by document MCP for
    `<Legal_Department_Master_Data>` / `<Sales_Excellence_Master_Data>`.
    """
    try:
        row = _master_store().upsert(
            placeholder_key=body.placeholder_key,
            content=body.content,
            category=body.category,
            active=body.active,
        )
    except MasterDataKeyError as error:
        raise _master_http(error) from error
    return MasterDataRecordResponse(**row)


@router.get(
    "/master-data",
    response_model=MasterDataListResponse,
    dependencies=[Depends(require_admin_key)],
    summary="List master-data blocks",
)
def list_master_data(
    category: str | None = Query(default=None, description="Filter: legal | sales | general"),
    limit: int = Query(default=200, ge=1, le=500),
) -> MasterDataListResponse:
    items = _master_store().list(category=category, limit=limit)
    return MasterDataListResponse(count=len(items), items=[MasterDataRecordResponse(**row) for row in items])


@router.get(
    "/master-data/{placeholder_key}",
    response_model=MasterDataRecordResponse,
    dependencies=[Depends(require_admin_key)],
    summary="Get one master-data block",
)
def get_master_data(placeholder_key: str) -> MasterDataRecordResponse:
    try:
        row = _master_store().get(placeholder_key)
    except MasterDataKeyError as error:
        raise _master_http(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return MasterDataRecordResponse(**row)


@router.put(
    "/master-data/{placeholder_key}",
    response_model=MasterDataRecordResponse,
    dependencies=[Depends(require_admin_key)],
    summary="Update a master-data block",
)
def update_master_data(
    placeholder_key: str,
    body: MasterDataUpdateRequest,
) -> MasterDataRecordResponse:
    try:
        _master_store().get(placeholder_key)
        row = _master_store().upsert(
            placeholder_key=placeholder_key,
            content=body.content,
            category=body.category or None,
            active=body.active,
        )
    except MasterDataKeyError as error:
        raise _master_http(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return MasterDataRecordResponse(**row)


@router.delete(
    "/master-data/{placeholder_key}",
    response_model=MasterDataDeletedResponse,
    dependencies=[Depends(require_admin_key)],
    summary="Delete a master-data block",
)
def delete_master_data(placeholder_key: str) -> MasterDataDeletedResponse:
    try:
        row = _master_store().delete(placeholder_key)
    except MasterDataKeyError as error:
        raise _master_http(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return MasterDataDeletedResponse(placeholder_key=row["placeholder_key"])
