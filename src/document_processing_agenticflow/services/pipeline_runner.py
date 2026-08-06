"""Run the LangGraph document pipeline for API/background jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from document_processing_agenticflow.core.request_context import bind_xid, get_xid
from document_processing_agenticflow.graph import invoke_document_graph
from document_processing_agenticflow.storage.job_store import JobStore


def run_document_job(
    job_id: str,
    *,
    skip_validation: bool = False,
    max_retries: int = 1,
    validation_threshold: float = 0.7,
    store: JobStore | None = None,
    xid: str | None = None,
) -> dict[str, Any]:
    """Execute LangGraph pipeline for a job already registered in SQLite."""
    job_store = store or JobStore()
    job = job_store.get_job(job_id)
    corr = xid or job.xid or get_xid()

    with bind_xid(corr, job_id=job_id):
        return _run_document_job_bound(
            job_id,
            job=job,
            job_store=job_store,
            skip_validation=skip_validation,
            max_retries=max_retries,
            validation_threshold=validation_threshold,
        )


def _run_document_job_bound(
    job_id: str,
    *,
    job: Any,
    job_store: JobStore,
    skip_validation: bool,
    max_retries: int,
    validation_threshold: float,
) -> dict[str, Any]:
    job_store.update_status(job_id, "processing")

    try:
        from document_processing_agenticflow.services.naming import build_contract_output_filename

        fallback_name = build_contract_output_filename(
            job_id, Path(job.template_path or "template.docx").name
        )
        result = invoke_document_graph(
            {
                "template_path": job.template_path,
                "data_path": job.data_path,
                "output_path": job.output_path
                or str(job_store.cfg.job_dir(job_id) / fallback_name),
                "errors": [],
                "status": "started",
                "retry_count": 0,
                "max_retries": max_retries,
                "validation_threshold": validation_threshold,
                "skip_validation": skip_validation,
            }
        )
    except Exception as exc:  # noqa: BLE001
        job_store.complete_job(job_id, error=str(exc))
        raise

    errors = result.get("errors") or []
    status = result.get("status")
    if status != "completed" or errors:
        msg = "; ".join(errors) if errors else f"Pipeline ended with status={status}"
        job_store.complete_job(job_id, error=msg)
        return {"job_id": job_id, "status": "failed", "errors": errors, "xid": get_xid()}

    confidence = result.get("confidence")
    validation = result.get("validation")
    extraction = result.get("extraction_validation")
    mapping = result.get("mapping")

    confidence_dict = confidence.model_dump() if confidence else None
    validation_dict = validation.model_dump() if validation else None
    extraction_dict = extraction.model_dump() if extraction else None

    mapper_llm = confidence.mapper_llm if confidence else None
    validator_llm = confidence.validator_llm if confidence else None
    if not mapper_llm and mapping and mapping.mapper_provider and mapping.mapper_model:
        mapper_llm = f"{mapping.mapper_provider}/{mapping.mapper_model}"

    result_snapshot = {
        "job_id": job_id,
        "xid": get_xid(),
        "status": "completed",
        "output_path": job.output_path,
        "mapper_llm": mapper_llm,
        "validator_llm": validator_llm,
        "scores_pct": (confidence_dict or {}).get("scores_pct") if confidence_dict else None,
        "confidence": confidence_dict,
        "validation": validation_dict,
        "extraction_validation": extraction_dict,
    }

    job_store.complete_job(
        job_id,
        confidence=confidence_dict,
        validation=validation_dict,
        extraction_validation=extraction_dict,
        result=result_snapshot,
        mapper_llm=mapper_llm,
        validator_llm=validator_llm,
    )

    return result_snapshot
