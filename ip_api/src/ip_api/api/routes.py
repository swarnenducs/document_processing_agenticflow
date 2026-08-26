"""FastAPI routes: document jobs + voice-to-text."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from ip_api.api.schemas import (
    HealthResponse,
    JobAcceptedResponse,
    JobCreateOptions,
    JobListResponse,
    JobStatusResponse,
    TraceByXidResponse,
    TranscriptionResponse,
    VoiceContractConfirmRequest,
    VoiceContractRequest,
    VoiceContractResponse,
)
from ip_api.api.dependencies import get_blob_store_dep, get_job_store, get_settings_dependency, get_template_store_dep
from ip_api.core.request_context import require_xid
from ip_api.core.settings import Settings, settings
from ip_api.services.job_events import get_job_event_hub, publish_job_stage
from ip_api.services.pipeline_runner import run_document_job
from ip_api.services.session_service import ensure_request_session
from ip_api.services.speech_to_text import transcribe_audio
from ip_api.storage.blob_store import BlobStore, is_blob_ref
from ip_api.storage.job_store import JobRecord, JobStore
from ip_api.storage.template_store import TemplateStore

router = APIRouter()
logger = logging.getLogger(__name__)

JobStoreDep = Annotated[JobStore, Depends(get_job_store)]
TemplateStoreDep = Annotated[TemplateStore, Depends(get_template_store_dep)]
BlobStoreDep = Annotated[BlobStore, Depends(get_blob_store_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings_dependency)]


def get_store() -> JobStore:
    """Resolve JobStore from the application context (background tasks / helpers)."""
    from ip_api.api.dependencies import get_app_context

    return get_app_context().job_store


def _attach_session(payload: dict[str, Any], session) -> dict[str, Any]:
    payload["session_id"] = session.session_id
    payload["user_id"] = session.user_id
    payload["user_email"] = session.user_email
    return payload


def _format_elapsed_ms(elapsed_ms: float) -> str:
    total_s = max(0.0, float(elapsed_ms) / 1000.0)
    if total_s < 60:
        return f"{total_s:.1f} s"
    minutes = int(total_s // 60)
    seconds = total_s - minutes * 60
    if minutes < 60:
        return f"{minutes}m {seconds:.1f}s"
    hours = minutes // 60
    minutes_rem = minutes % 60
    return f"{hours}h {minutes_rem}m {seconds:.0f}s"


def _coerce_elapsed_ms(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:  # noqa: BLE001
        pass
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _parse_iso(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pair_elapsed(ms: object, human: object) -> tuple[float | None, str | None]:
    coerced = _coerce_elapsed_ms(ms)
    label = human.strip() if isinstance(human, str) and human.strip() else None
    if coerced is not None:
        return coerced, label or _format_elapsed_ms(coerced)
    if label:
        return None, label
    return None, None


def _job_elapsed(
    result: dict[str, Any] | None,
    created_at: object | None,
    completed_at: object | None,
    *,
    elapsed_ms: object | None = None,
    elapsed: object | None = None,
) -> tuple[float | None, str | None]:
    """Prefer Document MCP wall time; fall back to columns, then created/completed stamps."""
    if isinstance(result, dict):
        pair = _pair_elapsed(result.get("elapsed_ms"), result.get("elapsed"))
        if pair != (None, None):
            return pair
    pair = _pair_elapsed(elapsed_ms, elapsed)
    if pair != (None, None):
        return pair
    start = _parse_iso(created_at)
    end = _parse_iso(completed_at)
    if start is None or end is None:
        return None, None
    try:
        if start.tzinfo is None and end.tzinfo is not None:
            start = start.replace(tzinfo=end.tzinfo)
        elif end.tzinfo is None and start.tzinfo is not None:
            end = end.replace(tzinfo=start.tzinfo)
        if end >= start:
            ms = (end - start).total_seconds() * 1000.0
            return round(ms, 1), _format_elapsed_ms(ms)
    except TypeError:
        return None, None
    return None, None


def _download_ready(status: str | None, output_path: str | None) -> bool:
    if status != "completed" or not output_path:
        return False
    return is_blob_ref(output_path) or Path(output_path).exists()

ALLOWED_AUDIO = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}


def _max_bytes(cfg: Settings | None = None) -> int:
    return (cfg or settings()).max_upload_mb * 1024 * 1024


async def _save_upload(
    upload: UploadFile,
    dest: Path,
    allowed_suffixes: set[str] | None = None,
    *,
    cfg: Settings | None = None,
) -> None:
    suffix = Path(upload.filename or "").suffix.lower()
    if allowed_suffixes and suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(allowed_suffixes)}",
        )
    content = await upload.read()
    limit = _max_bytes(cfg)
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {(cfg or settings()).max_upload_mb} MB",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


def _resolve_stored_template(
    template: UploadFile | None,
    folder_name: str | None,
    template_name: str | None,
    templates: TemplateStore,
):
    """Pick the template source: inline upload or a row in the admin library."""
    from ip_api.storage.template_store import DEFAULT_TEMPLATE_FOLDER, TemplateNameError

    named = bool((template_name or "").strip())
    has_upload = template is not None and bool(template.filename)
    if has_upload and named:
        raise HTTPException(
            status_code=400,
            detail="Send either a template upload or template_name, not both",
        )
    if not has_upload and not named:
        raise HTTPException(
            status_code=400,
            detail=(
                "A template is required: upload one, or pass template_name "
                f"(folder_name defaults to {DEFAULT_TEMPLATE_FOLDER})"
            ),
        )
    if not named:
        return None
    try:
        return templates.get(folder_name, template_name or "")
    except TemplateNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _materialize_stored_template(record, dest: Path, templates: TemplateStore) -> None:
    try:
        templates.materialize(record, dest)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=410,
            detail=f"Stored template '{record.location}' is no longer available: {exc}",
        ) from exc


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Gateway + downstream health",
)
async def health(
    cfg: SettingsDep,
    blob: BlobStoreDep,
) -> HealthResponse:
    """
    Cheap readiness for operators and load balancers.

    Returns SQL/Blob flags, whether mapper and validator LLM keys work, speech,
    and whether MAF (and its document/voice MCP catalogue) answered. `status` is
    `ok` only if the mapper LLM is configured; otherwise `degraded` but HTTP 200.
    """
    from ip_api.services.llm_factory import (
        is_mapper_available,
        is_validator_available,
        mapper_config,
        validator_config,
    )
    from ip_api.services.speech_to_text import resolve_speech_provider

    from ip_api.services.maf_client import maf_health, maf_base_url
    from ip_api.storage.db import build_database_url, engine_uses_mssql

    db_url = build_database_url()
    sql_ok: bool | None = None
    if cfg.uses_azure_sql:
        try:
            from ip_api.storage.db import get_engine
            from sqlalchemy import text

            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            sql_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Azure SQL health check failed: %s", exc)
            sql_ok = False

    blob_ok: bool | None = None
    if blob.enabled:
        blob_ok = blob.ping()
    mapper = mapper_config()
    validator = validator_config()
    mapper_ok = is_mapper_available()
    validator_ok = is_validator_available()
    try:
        resolve_speech_provider()
        speech_ok = True
    except Exception:  # noqa: BLE001
        speech_ok = False

    def _mcp_from_catalog(catalog: dict[str, Any], name: str) -> bool:
        for row in catalog.get("servers") or []:
            if isinstance(row, dict) and row.get("name") == name:
                return bool(row.get("available"))
        return False

    try:
        catalog = await asyncio.wait_for(maf_health(), timeout=2.5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MAF health probe failed: %s", exc)
        catalog = {"ok": False}
    if not isinstance(catalog, dict):
        catalog = {"ok": False}
    maf_ok = bool(catalog.get("ok"))
    doc_mcp_ok = (
        _mcp_from_catalog(catalog, "contract-autocreation-mcp")
        or _mcp_from_catalog(catalog, "template-auto-creation")
        or _mcp_from_catalog(catalog, "document")
    )
    voice_mcp_ok = _mcp_from_catalog(catalog, "voice-agent") or _mcp_from_catalog(catalog, "voice")
    maf_mode = "proxy"
    maf_base = maf_base_url()

    return HealthResponse(
        storage_base_path=str(cfg.storage_base_path),
        sqlite_database_path=str(cfg.sqlite_database_path),
        storage_backend="azure_blob" if blob.enabled else "local",
        azure_sql_server=cfg.azure_sql_server if engine_uses_mssql(db_url) else None,
        azure_sql_database=cfg.azure_sql_database if engine_uses_mssql(db_url) else None,
        azure_blob_container=cfg.azure_blob_container if blob.enabled else None,
        azure_sql_available=sql_ok,
        azure_blob_available=blob_ok,
        speech_provider=cfg.speech_provider,
        mapper_provider=mapper.provider,
        mapper_model=mapper.model,
        mapper_available=mapper_ok,
        validator_provider=validator.provider,
        validator_model=validator.model,
        validator_available=validator_ok,
        speech_available=speech_ok,
        document_mcp_available=doc_mcp_ok,
        voice_mcp_available=voice_mcp_ok,
        maf_available=maf_ok,
        maf_mode=maf_mode,
        maf_base_url=maf_base,
        status="ok" if mapper_ok else "degraded",
    )


# ---------------------------------------------------------------------------
# Document generation API
# ---------------------------------------------------------------------------


@router.post(
    "/documents/jobs",
    response_model=JobAcceptedResponse,
    status_code=202,
    tags=["documents"],
    summary="Create document job (template + JSON)",
    responses={
        202: {"description": "Accepted. Poll status_url or wait=true, then download."},
        400: {"description": "`data` is not a JSON object, or template missing/invalid."},
        404: {"description": "Named library template does not exist."},
    },
)
async def create_document_job(
    background_tasks: BackgroundTasks,
    store: JobStoreDep,
    templates: TemplateStoreDep,
    cfg: SettingsDep,
    data: str = Form(
        ...,
        description="JSON object sent as a request form field (not a file upload)",
    ),
    template: UploadFile | None = File(
        default=None, description="Word .docx template (omit to use a stored template)"
    ),
    folder_name: str | None = Form(
        default=None,
        description="Library folder for a stored template. Defaults to ipp_default_template.",
    ),
    template_name: str | None = Form(
        default=None,
        description="Stored template name (with optional folder_name)",
    ),
    skip_validation: bool = Form(default=False),
    max_retries: int | None = Form(
        default=None,
        description="Map→generate retries when the judge fails. Default: DOCUMENT_MAX_RETRIES (0-3).",
    ),
    validation_threshold: float | None = Form(
        default=None,
        description="Minimum judge score to accept (0-1). Default: DOCUMENT_VALIDATION_THRESHOLD.",
    ),
    optimized_flow: bool | None = Form(
        default=None,
        description=(
            "Use llm_optimization.json mapper cascade. Default: DOCUMENT_LLM_OPTIMIZATION_ENABLED."
        ),
    ),
    session_id: str | None = Form(default=None),
    user_id: str | None = Form(default=None),
    user_email: str | None = Form(default=None),
) -> JobAcceptedResponse:
    """
    Create a document generation job.

    Send **multipart/form-data**, not a JSON body.

    **Form fields**

    * `data` (required) — JSON object **as text**, not a file.
      Example: `{"party":"AVC"}`
    * Template — provide **one** of:
      * `template` — upload a `.docx` file, or
      * `template_name` — name in the admin library
        (`folder_name` defaults to `ipp_default_template`)

    **After 202**

    1. `GET /api/v1/documents/jobs/{job_id}?wait=true&timeout=180`
       until `status` is `completed` or `failed`, **or**
    2. WebSocket `ws://<host>/api/v1/documents/jobs/{job_id}/ws`
       (path is also returned as `ws_url`)
    3. `GET /api/v1/documents/jobs/{job_id}/download` when completed

    Optional form fields: `skip_validation`, `max_retries` (0–3),
    `validation_threshold` (0–1), `optimized_flow`, `session_id`,
    `user_id`, `user_email`.
    """
    from ip_api.flow_debug import flow_breakpoint

    flow_breakpoint(
        "create_document_job",
        template=getattr(template, "filename", None),
        session_id=session_id,
    )
    session = ensure_request_session(
        request_kind="document",
        session_id=session_id,
        user_id=user_id,
        user_email=user_email,
        path="/api/v1/documents/jobs",
    )

    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in `data`: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON root must be an object")

    stored_template = _resolve_stored_template(template, folder_name, template_name, templates)
    template_filename = (
        stored_template.template_name
        if stored_template is not None
        else (template.filename if template else None) or "template.docx"
    )

    job_id, _job_dir, template_path, data_path, output_path = store.create_job_paths(
        template_filename=template_filename,
    )

    if stored_template is not None:
        _materialize_stored_template(stored_template, template_path, templates)
    else:
        await _save_upload(template, template_path, allowed_suffixes={".docx"}, cfg=cfg)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    store.insert_job(job_id, template_path, data_path, output_path, xid=require_xid())

    use_opt = (
        cfg.document_llm_optimization_enabled
        if optimized_flow is None
        else optimized_flow
    )
    if use_opt:
        retries_out = max_retries
        threshold_out = validation_threshold
    else:
        retries_out = cfg.document_max_retries if max_retries is None else max_retries
        threshold_out = (
            cfg.document_validation_threshold
            if validation_threshold is None
            else validation_threshold
        )
    options = JobCreateOptions(
        skip_validation=skip_validation,
        max_retries=retries_out,
        validation_threshold=threshold_out,
        optimized_flow=use_opt,
    )

    corr = require_xid()
    publish_job_stage(job_id, "accepted", xid=corr)
    background_tasks.add_task(
        run_document_job,
        job_id,
        skip_validation=options.skip_validation,
        max_retries=options.max_retries,
        validation_threshold=options.validation_threshold,
        optimized_flow=options.optimized_flow,
        store=store,
        xid=corr,
    )

    base = f"/api/v1"
    return JobAcceptedResponse(
        job_id=job_id,
        xid=corr,
        session_id=session.session_id,
        user_id=session.user_id,
        user_email=session.user_email,
        status="pending",
        status_url=f"{base}/documents/jobs/{job_id}",
        download_url=f"{base}/documents/jobs/{job_id}/download",
        ws_url=f"{base}/documents/jobs/{job_id}/ws",
    )


@router.get(
    "/documents/jobs",
    response_model=JobListResponse,
    tags=["documents"],
    summary="List recent document jobs",
)
def list_document_jobs(store: JobStoreDep, limit: int = 50) -> JobListResponse:
    """Newest first. Each row includes `status` and `download_url` when the file is ready."""
    rows = store.list_document_jobs(limit=limit)
    jobs: list[JobStatusResponse] = []
    for row in rows:
        confidence = row.get("confidence")
        scores_pct = None
        if isinstance(confidence, dict):
            scores_pct = confidence.get("scores_pct")
        if scores_pct is None and isinstance(row.get("result"), dict):
            scores_pct = row["result"].get("scores_pct")
        elapsed_ms, elapsed = _job_elapsed(
            row.get("result") if isinstance(row.get("result"), dict) else None,
            row.get("created_at"),
            row.get("completed_at"),
            elapsed_ms=row.get("elapsed_ms"),
            elapsed=row.get("elapsed"),
        )
        download_url = None
        out = row.get("output_path")
        if _download_ready(row.get("status"), out):
            download_url = f"/api/v1/documents/jobs/{row['job_id']}/download"
        jobs.append(
            JobStatusResponse(
                job_id=row["job_id"],
                mcp=row.get("mcp"),
                xid=row.get("xid"),
                status=row["status"],
                template_path=row.get("template_path"),
                output_path=row.get("output_path"),
                error_message=row.get("error_message"),
                mapper_llm=row.get("mapper_llm"),
                validator_llm=row.get("validator_llm"),
                confidence=confidence,
                validation=row.get("validation"),
                extraction_validation=row.get("extraction_validation"),
                result=row.get("result"),
                scores_pct=scores_pct,
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                completed_at=row.get("completed_at"),
                elapsed_ms=elapsed_ms,
                elapsed=elapsed,
                download_url=download_url,
                sqlite_persisted=True,
            )
        )
    return JobListResponse(count=len(jobs), jobs=jobs)


def _job_status_response(job: JobRecord, store: JobStore | None = None) -> JobStatusResponse:
    download_url = None
    if _download_ready(job.status, job.output_path):
        download_url = f"/api/v1/documents/jobs/{job.id}/download"

    confidence = json.loads(job.confidence_json) if job.confidence_json else None
    validation = json.loads(job.validation_json) if job.validation_json else None
    extraction = (
        json.loads(job.extraction_validation_json)
        if job.extraction_validation_json
        else None
    )
    result = json.loads(job.result_json) if job.result_json else None

    scores_pct = None
    if confidence and isinstance(confidence, dict):
        scores_pct = confidence.get("scores_pct")
    if scores_pct is None and isinstance(result, dict):
        scores_pct = result.get("scores_pct")

    elapsed_ms, elapsed = _job_elapsed(
        result if isinstance(result, dict) else None,
        job.created_at,
        job.completed_at,
        elapsed_ms=job.elapsed_ms,
        elapsed=job.elapsed,
    )

    return JobStatusResponse(
        job_id=job.id,
        mcp=job.mcp,
        xid=job.xid,
        status=job.status,
        template_path=job.template_path,
        output_path=job.output_path,
        error_message=job.error_message,
        mapper_llm=job.mapper_llm,
        validator_llm=job.validator_llm,
        confidence=confidence,
        validation=validation,
        extraction_validation=extraction,
        result=result,
        scores_pct=scores_pct,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        elapsed_ms=elapsed_ms,
        elapsed=elapsed,
        download_url=download_url,
        sqlite_persisted=True,
        accuracy_report=(store or get_store()).get_accuracy_report(job.id),
    )


@router.get(
    "/documents/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["documents"],
    summary="Get document job status",
)
async def get_document_job(
    job_id: str,
    store: JobStoreDep,
    wait: bool = Query(
        default=False,
        description="Long-poll: hold until status is completed/failed (or timeout).",
    ),
    timeout: float = Query(
        default=180.0,
        ge=1.0,
        le=600.0,
        description="Max seconds to wait when wait=true.",
    ),
) -> JobStatusResponse:
    """
    Return current `status`: `pending`, `processing`, `completed`, or `failed`.

    Set `wait=true` to **long-poll** (server holds until terminal or `timeout`
    seconds, default 180). Then call `/download` if `status` is `completed`.
    `409` on download if the job is not finished.
    """
    try:
        job = store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not wait or job.status in {"completed", "failed"}:
        return _job_status_response(job, store)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        try:
            job = store.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if job.status in {"completed", "failed"}:
            return _job_status_response(job, store)

    return _job_status_response(job, store)


@router.get(
    "/documents/jobs/{job_id}/accuracy",
    tags=["documents"],
    summary="Accuracy / confidence report",
)
def get_document_accuracy(job_id: str, store: JobStoreDep) -> dict[str, Any]:
    """Persisted judge/mapper scores for this job. **404** if the job or report is missing."""
    try:
        store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = store.get_accuracy_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No accuracy report for job {job_id}")
    return report


@router.websocket("/documents/jobs/{job_id}/ws")
async def document_job_progress_ws(websocket: WebSocket, job_id: str, store: JobStoreDep) -> None:
    """
    Live pipeline stages (`extraction`, `mapped`, `validated`, `completed`, …).

    Swagger **Try it out** does not drive WebSockets. Connect with a WS client to
    `ws://127.0.0.1:8000/api/v1/documents/jobs/{job_id}/ws` (or `wss://` in Azure).
    """
    await websocket.accept()
    try:
        job = store.get_job(job_id)
    except KeyError:
        await websocket.send_json(
            {
                "job_id": job_id,
                "stage": "failed",
                "message": "Job not found",
                "progress": 1.0,
                "terminal": True,
                "error": f"Job not found: {job_id}",
            }
        )
        await websocket.close(code=4404)
        return

    # Already finished — one terminal event (no duplicate history/snapshot).
    if job.status in {"completed", "failed"}:
        await websocket.send_json(
            {
                "job_id": job.id,
                "stage": job.status,
                "message": "Job completed" if job.status == "completed" else "Job failed",
                "progress": 1.0,
                "xid": job.xid,
                "terminal": True,
                "error": job.error_message,
            }
        )
        await websocket.close()
        return

    hub = get_job_event_hub()
    try:
        seen: set[str] = set()
        async for event in hub.subscribe(job_id):
            stage = str(event.get("stage") or "")
            # Deduplicate consecutive / repeated stage names from history+live races.
            if stage and stage in seen and not event.get("terminal"):
                continue
            if stage:
                seen.add(stage)
            await websocket.send_json(event)
            if event.get("terminal") or stage in {"completed", "failed"}:
                break
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await websocket.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
        return

    try:
        await websocket.close()
    except Exception:  # noqa: BLE001
        pass


@router.get(
    "/traces/{xid}",
    response_model=TraceByXidResponse,
    tags=["traces"],
    summary="Trace logs by xid",
)
def get_trace_by_xid(xid: str, store: JobStoreDep) -> TraceByXidResponse:
    """All HTTP/tool/LLM events and jobs sharing this correlation id (`X-Request-ID`)."""
    payload = store.get_trace_by_xid(xid.strip())
    return TraceByXidResponse(**payload)


@router.get(
    "/documents/jobs/{job_id}/download",
    tags=["documents"],
    summary="Download generated Word file",
    responses={
        200: {"description": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        404: {"description": "Job or output file missing."},
        409: {"description": "Job not completed yet."},
    },
)
def download_document(job_id: str, store: JobStoreDep) -> FileResponse:
    """Binary `.docx`. Call only when GET status is `completed`."""
    try:
        job = store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job not ready. Status: {job.status}")
    try:
        output = store.resolve_output_file(job)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=output,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=output.name,
    )


@router.delete(
    "/documents/jobs/{job_id}",
    status_code=204,
    tags=["documents"],
    summary="Delete document job",
)
def delete_document_job(job_id: str, store: JobStoreDep) -> None:
    """Removes the job row (and local files when stored locally). **204** empty body."""
    try:
        store.delete_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Voice → natural language text API
# ---------------------------------------------------------------------------


@router.post(
    "/audio/transcribe",
    response_model=TranscriptionResponse,
    tags=["audio"],
    summary="Speech-to-text (audio file)",
)
async def transcribe_voice(
    store: JobStoreDep,
    cfg: SettingsDep,
    audio: UploadFile = File(..., description="Audio file (mp3, wav, m4a, webm, …)"),
    language: str | None = Form(
        default=None,
        description="Optional ISO-639-1 language hint (e.g. en)",
    ),
    provider: str | None = Form(
        default=None,
        description="Override SPEECH_PROVIDER: auto | openai | groq",
    ),
) -> TranscriptionResponse:
    """
    Upload audio (`mp3`, `wav`, `m4a`, `webm`, …) → transcript text.

    Uses OpenAI Whisper or Groq. `SPEECH_PROVIDER=auto` picks OpenAI if
    `OPENAI_API_KEY` is set, else Groq. This does **not** start a contract.
    For STT + contract in one call use `POST /api/v1/voice/contract/from-audio`.
    """
    transcription_id = str(uuid.uuid4())
    suffix = Path(audio.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type '{suffix}'. Allowed: {sorted(ALLOWED_AUDIO)}",
        )

    audio_dir = cfg.audio_root / transcription_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"input{suffix}"

    await _save_upload(audio, audio_path, allowed_suffixes=ALLOWED_AUDIO, cfg=cfg)

    try:
        result = transcribe_audio(audio_path, language=language, provider=provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc

    store.save_transcription(
        transcription_id,
        audio_path,
        result.text,
        result.provider,
        result.model,
    )

    return TranscriptionResponse(
        transcription_id=transcription_id,
        text=result.text,
        provider=result.provider,
        model=result.model,
        language=result.language,
    )


@router.get(
    "/audio/transcriptions/{transcription_id}",
    tags=["audio"],
    summary="Get saved transcription",
)
def get_transcription(transcription_id: str, store: JobStoreDep) -> dict[str, Any]:
    """Row written by `/audio/transcribe` or `/voice/contract/from-audio`."""
    try:
        return store.get_transcription(transcription_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/voice/contract",
    response_model=VoiceContractResponse,
    tags=["voice"],
    summary="Start contract from transcript (HITL)",
)
async def voice_contract_from_text(body: VoiceContractRequest) -> VoiceContractResponse:
    """
    JSON body: `transcript` is required (already-transcribed speech or typed text).

    Calls MAF → voice MCP `start_voice_contract`. Often returns `thread_id` and
    asks for confirmation. Next: `POST /api/v1/voice/contract/confirm` with that
    `thread_id` plus `legal_entity` and `contract_reference_number`.

    Set `auto_create: true` only if you want to skip HITL (not the usual path).
    """
    from ip_api.flow_debug import flow_breakpoint

    from ip_api.services.maf_client import invoke_tool

    flow_breakpoint("voice_contract_from_text", transcript=body.transcript, session_id=body.session_id)
    session = ensure_request_session(
        request_kind="voice",
        session_id=body.session_id,
        user_id=body.user_id,
        user_email=body.user_email,
        path="/api/v1/voice/contract",
    )
    try:
        payload = await invoke_tool(
            "voice",
            "start_voice_contract",
            {"transcript": body.transcript, "auto_create": body.auto_create},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice call failed: {exc}") from exc
    if not isinstance(payload, dict):
        payload = {"ok": False, "message": str(payload)}
    return VoiceContractResponse(**_attach_session(payload, session))


@router.post(
    "/voice/contract/confirm",
    response_model=VoiceContractResponse,
    tags=["voice"],
    summary="Confirm HITL voice contract",
)
async def voice_contract_confirm(body: VoiceContractConfirmRequest) -> VoiceContractResponse:
    """
    Resume after start. Send `legal_entity` (e.g. AVC), `contract_reference_number`
    (e.g. CR-1001), `thread_id` from the start response, and `user_text` such as `yes`.
    """
    from ip_api.flow_debug import flow_breakpoint

    from ip_api.services.maf_client import invoke_tool

    flow_breakpoint(
        "voice_contract_confirm",
        thread_id=body.thread_id,
        legal_entity=body.legal_entity,
    )
    session = ensure_request_session(
        request_kind="voice",
        session_id=body.session_id,
        user_id=body.user_id,
        user_email=body.user_email,
        path="/api/v1/voice/contract/confirm",
    )
    try:
        payload = await invoke_tool(
            "voice",
            "confirm_voice_contract",
            {
                "legal_entity": body.legal_entity,
                "contract_reference_number": body.contract_reference_number,
                "thread_id": body.thread_id,
                "user_text": body.user_text or "yes",
                "transcript": body.transcript,
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice confirm failed: {exc}") from exc
    if not isinstance(payload, dict):
        payload = {"ok": False, "message": str(payload)}
    return VoiceContractResponse(**_attach_session(payload, session))


@router.post(
    "/voice/contract/from-audio",
    response_model=VoiceContractResponse,
    tags=["voice"],
    summary="Transcribe audio then start contract",
)
async def voice_contract_from_audio(
    store: JobStoreDep,
    cfg: SettingsDep,
    audio: UploadFile = File(..., description="Audio file (mp3, wav, m4a, webm, …)"),
    language: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    auto_create: bool = Form(default=False),
    session_id: str | None = Form(default=None),
    user_id: str | None = Form(default=None),
    user_email: str | None = Form(default=None),
) -> VoiceContractResponse:
    """
    Multipart: `audio` file, optional `language`, `provider`, `auto_create`.

    Transcribes in the gateway, then the same start path as `/voice/contract`.
    Confirm still uses `/voice/contract/confirm` if HITL is required.
    """
    from ip_api.services.maf_client import invoke_tool

    session = ensure_request_session(
        request_kind="voice",
        session_id=session_id,
        user_id=user_id,
        user_email=user_email,
        path="/api/v1/voice/contract/from-audio",
    )
    transcription_id = str(uuid.uuid4())
    suffix = Path(audio.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type '{suffix}'. Allowed: {sorted(ALLOWED_AUDIO)}",
        )

    audio_dir = cfg.audio_root / transcription_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"input{suffix}"
    await _save_upload(audio, audio_path, allowed_suffixes=ALLOWED_AUDIO, cfg=cfg)

    try:
        transcription = transcribe_audio(audio_path, language=language, provider=provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc

    store.save_transcription(
        transcription_id,
        audio_path,
        transcription.text,
        transcription.provider,
        transcription.model,
    )

    try:
        payload = await invoke_tool(
            "voice",
            "start_voice_contract",
            {"transcript": transcription.text, "auto_create": auto_create},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice call failed: {exc}") from exc
    if not isinstance(payload, dict):
        payload = {"ok": False, "message": str(payload)}
    payload["transcription_id"] = transcription_id
    payload["provider"] = transcription.provider
    payload["model"] = transcription.model
    return VoiceContractResponse(**_attach_session(payload, session))


async def _voice_contract_row(contract_id: str, store: JobStore) -> dict[str, Any]:
    from ip_api.services.maf_client import invoke_tool

    try:
        listed = await invoke_tool("voice", "list_voice_contracts", {"limit": 200})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent list contracts failed: {exc}") from exc
    rows = (listed or {}).get("contracts") if isinstance(listed, dict) else None
    for row in rows or []:
        if str(row.get("contract_id") or row.get("id") or "") == contract_id:
            return row
    try:
        return store.get_voice_contract(contract_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/voice/contracts/{contract_id}",
    tags=["voice"],
    summary="Get voice contract metadata",
)
async def get_voice_contract(contract_id: str, store: JobStoreDep) -> dict[str, Any]:
    """Looks up via MAF list, then local store. **404** if unknown."""
    return await _voice_contract_row(contract_id, store)


@router.get(
    "/voice/contracts/{contract_id}/download",
    tags=["voice"],
    summary="Download voice contract file",
)
async def download_voice_contract(
    contract_id: str,
    store: JobStoreDep,
    cfg: SettingsDep,
    format: str = Query(
        default="docx",
        description="`docx` or `txt`. File lives on the voice MCP host disk.",
    ),
) -> FileResponse:
    """Binary contract. Query `format=txt` for plain text when available."""
    row = await _voice_contract_row(contract_id, store)

    path = row.get("contract_file")
    if format.lower() == "txt":
        if path:
            txt_candidate = Path(path).with_suffix(".txt")
            if txt_candidate.is_file():
                path = str(txt_candidate)
        if not path or not str(path).endswith(".txt"):
            payload = row.get("contract_payload") or {}
            if payload:
                from ip_api.services.contract_text import render_contract_text

                tmp = cfg.storage_base_path / "voice_contracts" / f"{contract_id}.txt"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(render_contract_text(payload), encoding="utf-8")
                path = str(tmp)

    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Contract file not found")

    if str(path).endswith(".txt"):
        return FileResponse(path, media_type="text/plain", filename=f"contract_{contract_id}.txt")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"contract_{contract_id}.docx",
    )


@router.get(
    "/voice/contracts",
    tags=["voice"],
    summary="List voice contracts",
)
async def list_voice_contracts(limit: int = 50) -> dict[str, Any]:
    """Via MAF → voice MCP `list_voice_contracts`. Newest/limit depends on MCP."""
    from ip_api.services.maf_client import invoke_tool

    try:
        payload = await invoke_tool("voice", "list_voice_contracts", {"limit": limit})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent list contracts failed: {exc}") from exc
    if isinstance(payload, dict):
        return payload
    return {"count": 0, "contracts": []}
