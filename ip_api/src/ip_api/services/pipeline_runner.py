"""Run the document pipeline by calling document-processing-mcp with blob refs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ip_api.core.request_context import bind_xid, get_xid
from ip_api.services import maf_client
from ip_api.services.job_events import publish_job_stage
from ip_api.storage.blob_store import is_blob_ref
from ip_api.storage.job_store import JobStore

logger = logging.getLogger(__name__)


async def run_document_job(
    job_id: str,
    *,
    skip_validation: bool = False,
    max_retries: int = 1,
    validation_threshold: float = 0.7,
    store: JobStore | None = None,
    xid: str | None = None,
) -> dict[str, Any]:
    """Call Document MCP for a job already registered (blob refs or local paths)."""
    from ip_api.flow_debug import flow_breakpoint

    flow_breakpoint("run_document_job", job_id=job_id, xid=xid)
    job_store = store or JobStore()
    job = job_store.get_job(job_id)
    corr = xid or job.xid or get_xid()

    with bind_xid(corr, job_id=job_id):
        return await _run_document_job_bound(
            job_id,
            job=job,
            job_store=job_store,
            skip_validation=skip_validation,
            max_retries=max_retries,
            validation_threshold=validation_threshold,
        )


async def _run_document_job_bound(
    job_id: str,
    *,
    job: Any,
    job_store: JobStore,
    skip_validation: bool,
    max_retries: int,
    validation_threshold: float,
) -> dict[str, Any]:
    xid = get_xid()
    job_store.update_status(job_id, "processing")
    publish_job_stage(job_id, "processing", xid=xid)

    try:
        payload = await maf_client.invoke_tool(
            "document",
            "generate_document",
            {
                "template_path": job.template_path,
                "data_path": job.data_path,
                "output_path": job.output_path,
                "job_id": job_id,
                "xid": xid,
                "skip_validation": skip_validation,
                "max_retries": max_retries,
                "validation_threshold": validation_threshold,
            },
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"contract_autocreation_mcp returned unexpected payload: {payload!r}")
    except Exception as exc:  # noqa: BLE001
        try:
            job_store.complete_job(job_id, error=str(exc))
        except Exception as store_exc:  # noqa: BLE001
            logger.warning("Could not persist failed job %s: %s", job_id, store_exc)
        try:
            publish_job_stage(job_id, "failed", xid=xid, error=str(exc))
        except Exception as pub_exc:  # noqa: BLE001
            logger.warning("Could not publish failed stage for %s: %s", job_id, pub_exc)
        return {"job_id": job_id, "status": "failed", "errors": [str(exc)], "xid": xid}

    refreshed = job_store.get_job(job_id)
    mcp_status = str(payload.get("status") or "")
    errors = payload.get("errors") or []
    error_msg = payload.get("error") or (
        "; ".join(str(e) for e in errors) if errors else None
    )
    ok = bool(payload.get("ok")) and mcp_status == "completed"

    if payload.get("db_updated") and refreshed.status in {"completed", "failed"}:
        stage = refreshed.status
        if stage == "failed" or not ok:
            publish_job_stage(job_id, "failed", xid=xid, error=refreshed.error_message or error_msg)
            return {
                "job_id": job_id,
                "status": "failed",
                "errors": errors,
                "xid": xid,
                "output_path": refreshed.output_path,
                "elapsed_ms": payload.get("elapsed_ms") if payload.get("elapsed_ms") is not None else refreshed.elapsed_ms,
                "elapsed": payload.get("elapsed") or refreshed.elapsed,
            }
        if refreshed.elapsed is None and (
            payload.get("elapsed") or payload.get("elapsed_ms") is not None
        ):
            job_store.complete_job(
                job_id,
                confidence=payload.get("confidence") if isinstance(payload.get("confidence"), dict) else None,
                validation=payload.get("validation") if isinstance(payload.get("validation"), dict) else None,
                extraction_validation=payload.get("extraction_validation")
                if isinstance(payload.get("extraction_validation"), dict)
                else None,
                result={
                    "status": "completed",
                    "elapsed_ms": payload.get("elapsed_ms"),
                    "elapsed": payload.get("elapsed"),
                    "output_path": refreshed.output_path or payload.get("output_path"),
                },
                mapper_llm=payload.get("mapper_llm"),
                validator_llm=payload.get("validator_llm"),
                output_path=refreshed.output_path or payload.get("output_path"),
            )
            refreshed = job_store.get_job(job_id)
        publish_job_stage(job_id, "completed", xid=xid)
        return {
            "job_id": job_id,
            "xid": xid,
            "status": "completed",
            "output_path": refreshed.output_path or payload.get("output_path"),
            "mapper_llm": payload.get("mapper_llm"),
            "validator_llm": payload.get("validator_llm"),
            "scores_pct": (payload.get("confidence") or {}).get("scores_pct")
            if isinstance(payload.get("confidence"), dict)
            else None,
            "confidence": payload.get("confidence"),
            "validation": payload.get("validation"),
            "extraction_validation": payload.get("extraction_validation"),
            "elapsed_ms": payload.get("elapsed_ms") if payload.get("elapsed_ms") is not None else refreshed.elapsed_ms,
            "elapsed": payload.get("elapsed") or refreshed.elapsed,
        }

    stored_output = payload.get("output_path") or job.output_path
    local = Path(str(stored_output)) if stored_output else None
    if local and local.exists() and not is_blob_ref(stored_output):
        stored_output = job_store.persist_output(job_id, local)

    if not ok:
        msg = error_msg or f"Pipeline ended with status={mcp_status or 'unknown'}"
        job_store.complete_job(
            job_id,
            error=msg,
            confidence=payload.get("confidence") if isinstance(payload.get("confidence"), dict) else None,
            validation=payload.get("validation") if isinstance(payload.get("validation"), dict) else None,
            extraction_validation=payload.get("extraction_validation")
            if isinstance(payload.get("extraction_validation"), dict)
            else None,
            output_path=stored_output,
        )
        publish_job_stage(job_id, "failed", xid=xid, error=msg)
        return {"job_id": job_id, "status": "failed", "errors": errors, "xid": xid}

    result_snapshot = {
        "job_id": job_id,
        "xid": xid,
        "status": "completed",
        "output_path": stored_output,
        "mapper_llm": payload.get("mapper_llm"),
        "validator_llm": payload.get("validator_llm"),
        "scores_pct": (payload.get("confidence") or {}).get("scores_pct")
        if isinstance(payload.get("confidence"), dict)
        else None,
        "confidence": payload.get("confidence"),
        "validation": payload.get("validation"),
        "extraction_validation": payload.get("extraction_validation"),
        "elapsed_ms": payload.get("elapsed_ms"),
        "elapsed": payload.get("elapsed"),
    }
    job_store.complete_job(
        job_id,
        confidence=result_snapshot["confidence"]
        if isinstance(result_snapshot["confidence"], dict)
        else None,
        validation=result_snapshot["validation"]
        if isinstance(result_snapshot["validation"], dict)
        else None,
        extraction_validation=result_snapshot["extraction_validation"]
        if isinstance(result_snapshot["extraction_validation"], dict)
        else None,
        result=result_snapshot,
        mapper_llm=payload.get("mapper_llm"),
        validator_llm=payload.get("validator_llm"),
        output_path=stored_output,
    )
    publish_job_stage(job_id, "completed", xid=xid)
    return result_snapshot
