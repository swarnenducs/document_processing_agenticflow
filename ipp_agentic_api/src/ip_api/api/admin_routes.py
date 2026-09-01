"""Admin routes for the default Word template library.

Upload a template once to ``{folder_name}/{template_name}``. The default folder
is ``ipp_pricing_default_template``. On Azure Blob that is
``{AZURE_BLOB_TEMPLATE_PREFIX}/ipp_pricing_default_template/{name}.docx``.
Jobs can then name that template instead of re-uploading the .docx.
"""

from __future__ import annotations

import secrets

from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile

from ip_api.api.dependencies import get_settings_dependency, get_template_store_dep
from ip_api.api.schemas import (
    AdminTokenRequest,
    AdminTokenResponse,
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
from ip_api.services.admin_jwt import issue_admin_jwt, jwt_is_valid
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
AUTH_HEADER = "Authorization"

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

TemplateStoreDep = Annotated[TemplateStore, Depends(get_template_store_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings_dependency)]


def _matches_static_key(presented: str, expected: str) -> bool:
    if not presented or not expected or len(presented) != len(expected):
        return False
    return secrets.compare_digest(presented, expected)


def _presented_admin_secret(
    x_admin_api_key: str | None,
    authorization: str | None,
) -> str | None:
    raw = (x_admin_api_key or "").strip()
    if raw:
        return raw
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def require_admin_key(
    cfg: SettingsDep,
    x_admin_api_key: str | None = Header(
        default=None,
        alias=ADMIN_KEY_HEADER,
        description=(
            "Env ADMIN_API_KEY, or a PyJWT from POST /api/v1/admin/token. "
            "Authorization: Bearer is also accepted."
        ),
    ),
    authorization: str | None = Header(
        default=None,
        alias=AUTH_HEADER,
        description="Bearer <PyJWT from POST /api/v1/admin/token>",
    ),
) -> None:
    presented = _presented_admin_secret(x_admin_api_key, authorization)
    configured = (cfg.admin_api_key or "").strip()
    if presented and configured and _matches_static_key(presented, configured):
        return
    if presented and jwt_is_valid(presented, cfg):
        return
    if not presented:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing admin credential. Call POST /api/v1/admin/token, then send "
                f"{ADMIN_KEY_HEADER} or Authorization: Bearer <access_token>."
            ),
        )
    raise HTTPException(
        status_code=401,
        detail=f"Invalid {ADMIN_KEY_HEADER} / Bearer token (expired, forged, or wrong key).",
    )


def _require_mint_key(
    cfg: Settings,
    *,
    header_key: str | None,
    body_key: str | None,
) -> None:
    """When ADMIN_API_KEY is set, minting a JWT requires that key."""
    configured = (cfg.admin_api_key or "").strip()
    if not configured:
        return
    presented = (header_key or body_key or "").strip()
    if not _matches_static_key(presented, configured):
        raise HTTPException(
            status_code=401,
            detail=(
                "ADMIN_API_KEY is set. Send it as X-Admin-Api-Key (or JSON admin_key) "
                "to mint a JWT."
            ),
        )


def _token_response(cfg: Settings, ttl_seconds: int | None) -> AdminTokenResponse:
    token, expires_in, expires_at = issue_admin_jwt(cfg, ttl_seconds=ttl_seconds)
    return AdminTokenResponse(
        access_token=token,
        expires_in=expires_in,
        expires_at=expires_at,
    )


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
    "/token",
    response_model=AdminTokenResponse,
    summary="Mint a PyJWT admin access token",
)
def issue_admin_token(
    cfg: SettingsDep,
    body: AdminTokenRequest = Body(default_factory=AdminTokenRequest),
    x_admin_api_key: str | None = Header(default=None, alias=ADMIN_KEY_HEADER),
) -> AdminTokenResponse:
    """
    Return a signed HS256 JWT (`access_token`) for later admin calls.

    * If env `ADMIN_API_KEY` is **set**: send that key as `X-Admin-Api-Key`
      or JSON `admin_key` to mint.
    * If env `ADMIN_API_KEY` is **empty**: this call is open (local/UI bootstrap).
      Set `ADMIN_API_KEY` (and optionally `ADMIN_JWT_SECRET`) in Azure.

    Then call templates / master-data with
    `Authorization: Bearer <access_token>` or `X-Admin-Api-Key: <access_token>`.
    Default lifetime: `ADMIN_TOKEN_TTL_SECONDS` (8 hours).
    """
    _require_mint_key(cfg, header_key=x_admin_api_key, body_key=body.admin_key)
    return _token_response(cfg, body.ttl_seconds)


@router.get(
    "/token",
    response_model=AdminTokenResponse,
    summary="Mint a PyJWT admin access token (GET alias)",
)
def issue_admin_token_get(
    cfg: SettingsDep,
    x_admin_api_key: str | None = Header(default=None, alias=ADMIN_KEY_HEADER),
    ttl_seconds: int | None = Query(default=None, ge=60, le=604800),
) -> AdminTokenResponse:
    """Same as POST `/token`. Convenient for Swagger Try it out."""
    _require_mint_key(cfg, header_key=x_admin_api_key, body_key=None)
    return _token_response(cfg, ttl_seconds)


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

    Header **`X-Admin-Api-Key`** or **`Authorization: Bearer`** must be env
    `ADMIN_API_KEY` **or** a JWT from `POST /api/v1/admin/token`. Multipart: `file`,
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
