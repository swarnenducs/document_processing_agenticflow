"""Run the LangGraph document pipeline for API/background jobs."""

from __future__ import annotations

from typing import Any

from document_processing_agenticflow.graph import build_graph
from document_processing_agenticflow.storage.job_store import JobStore


def run_document_job(
    job_id: str,
    *,
    skip_validation: bool = False,
    max_retries: int = 1,
    validation_threshold: float = 0.7,
    store: JobStore | None = None,
) -> dict[str, Any]:
    """Execute LangGraph pipeline for a job already registered in SQLite."""
    job_store = store or JobStore()
    job = job_store.get_job(job_id)

    job_store.update_status(job_id, "processing")

    try:
        graph = build_graph()
        result = graph.invoke(
            {
                "template_path": job.template_path,
                "data_path": job.data_path,
                "output_path": job.output_path or str(
                    job_store.cfg.job_dir(job_id) / "output.docx"
                ),
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
        return {"job_id": job_id, "status": "failed", "errors": errors}

    confidence = result.get("confidence")
    validation = result.get("validation")
    mapping = result.get("mapping")

    confidence_dict = confidence.model_dump() if confidence else None
    validation_dict = validation.model_dump() if validation else None

    job_store.complete_job(
        job_id,
        confidence=confidence_dict,
        validation=validation_dict,
        mapper_llm=confidence.mapper_llm if confidence else None,
        validator_llm=confidence.validator_llm if confidence else None,
    )

    return {
        "job_id": job_id,
        "status": "completed",
        "output_path": job.output_path,
        "mapper_llm": mapping.mapper_provider + "/" + mapping.mapper_model
        if mapping and mapping.mapper_provider and mapping.mapper_model
        else None,
        "confidence": confidence_dict,
        "validation": validation_dict,
    }
