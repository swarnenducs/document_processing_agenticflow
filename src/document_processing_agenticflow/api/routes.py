"""FastAPI routes: document jobs + voice-to-text."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from document_processing_agenticflow.api.schemas import (
    HealthResponse,
    JobAcceptedResponse,
    JobCreateOptions,
    JobStatusResponse,
    TranscriptionResponse,
    VoiceContractConfirmRequest,
    VoiceContractRequest,
    VoiceContractResponse,
)
from document_processing_agenticflow.core.settings import settings
from document_processing_agenticflow.services.pipeline_runner import run_document_job
from document_processing_agenticflow.services.speech_to_text import transcribe_audio
from document_processing_agenticflow.services.voice_contract_workflow import (
    confirm_voice_contract,
    run_voice_contract_workflow,
)
from document_processing_agenticflow.storage.job_store import JobStore

router = APIRouter()
_store: JobStore | None = None


def get_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore()
    return _store

ALLOWED_AUDIO = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}


def _max_bytes() -> int:
    return settings().max_upload_mb * 1024 * 1024


async def _save_upload(upload: UploadFile, dest: Path, allowed_suffixes: set[str] | None = None) -> None:
    suffix = Path(upload.filename or "").suffix.lower()
    if allowed_suffixes and suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(allowed_suffixes)}",
        )
    content = await upload.read()
    if len(content) > _max_bytes():
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {settings().max_upload_mb} MB",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    from document_processing_agenticflow.services.llm_factory import (
        is_mapper_available,
        is_validator_available,
        mapper_config,
        validator_config,
    )
    from document_processing_agenticflow.services.speech_to_text import resolve_speech_provider

    cfg = settings()
    mapper = mapper_config()
    validator = validator_config()
    mapper_ok = is_mapper_available()
    validator_ok = is_validator_available()
    try:
        resolve_speech_provider()
        speech_ok = True
    except Exception:  # noqa: BLE001
        speech_ok = False

    return HealthResponse(
        storage_base_path=str(cfg.storage_base_path),
        sqlite_database_path=str(cfg.sqlite_database_path),
        speech_provider=cfg.speech_provider,
        mapper_provider=mapper.provider,
        mapper_model=mapper.model,
        mapper_available=mapper_ok,
        validator_provider=validator.provider,
        validator_model=validator.model,
        validator_available=validator_ok,
        speech_available=speech_ok,
        status="ok" if mapper_ok else "degraded",
    )


# ---------------------------------------------------------------------------
# Document generation API
# ---------------------------------------------------------------------------


@router.post("/documents/jobs", response_model=JobAcceptedResponse, status_code=202)
async def create_document_job(
    background_tasks: BackgroundTasks,
    template: UploadFile = File(..., description="Word .docx template"),
    data_json: UploadFile | None = File(
        default=None, description="JSON data file (alternative to data field)"
    ),
    data: str | None = Form(
        default=None,
        description="JSON object as string (alternative to data_json file)",
    ),
    skip_validation: bool = Form(default=False),
    max_retries: int = Form(default=1),
    validation_threshold: float = Form(default=0.7),
) -> JobAcceptedResponse:
    """
    Upload a Word template + JSON data model → async LangGraph job.

    Returns job_id immediately; poll GET /documents/jobs/{job_id} then download.
    """
    if not data and not data_json:
        raise HTTPException(status_code=400, detail="Provide `data` (form JSON string) or `data_json` file")

    job_id, _job_dir, template_path, data_path, output_path = get_store().create_job_paths(
        template_filename=template.filename or "template.docx",
    )

    await _save_upload(template, template_path, allowed_suffixes={".docx"})

    if data_json:
        # Always save as data.json (avoids issues with spaces in uploaded filenames)
        await _save_upload(data_json, data_path, allowed_suffixes={".json"})
        # Re-validate JSON parses
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON file: {exc}") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON root must be an object")
        data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        try:
            payload = json.loads(data or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in `data`: {exc}") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON root must be an object")
        data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    get_store().insert_job(job_id, template_path, data_path, output_path)

    options = JobCreateOptions(
        skip_validation=skip_validation,
        max_retries=max_retries,
        validation_threshold=validation_threshold,
    )

    background_tasks.add_task(
        run_document_job,
        job_id,
        skip_validation=options.skip_validation,
        max_retries=options.max_retries,
        validation_threshold=options.validation_threshold,
        store=get_store(),
    )

    base = f"/api/v1"
    return JobAcceptedResponse(
        job_id=job_id,
        status="pending",
        status_url=f"{base}/documents/jobs/{job_id}",
        download_url=f"{base}/documents/jobs/{job_id}/download",
    )


@router.get("/documents/jobs/{job_id}", response_model=JobStatusResponse)
def get_document_job(job_id: str) -> JobStatusResponse:
    try:
        job = get_store().get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    download_url = None
    if job.status == "completed" and job.output_path and Path(job.output_path).exists():
        download_url = f"/api/v1/documents/jobs/{job_id}/download"

    confidence = json.loads(job.confidence_json) if job.confidence_json else None
    validation = json.loads(job.validation_json) if job.validation_json else None

    scores_pct = None
    if confidence and isinstance(confidence, dict):
        scores_pct = confidence.get("scores_pct")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        template_path=job.template_path,
        output_path=job.output_path,
        error_message=job.error_message,
        mapper_llm=job.mapper_llm,
        validator_llm=job.validator_llm,
        confidence=confidence,
        validation=validation,
        scores_pct=scores_pct,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        download_url=download_url,
    )


@router.get("/documents/jobs/{job_id}/download")
def download_document(job_id: str) -> FileResponse:
    try:
        job = get_store().get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job not ready. Status: {job.status}")
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=job.output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=Path(job.output_path).name,
    )


@router.delete("/documents/jobs/{job_id}", status_code=204)
def delete_document_job(job_id: str) -> None:
    try:
        get_store().delete_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Voice → natural language text API
# ---------------------------------------------------------------------------


@router.post("/audio/transcribe", response_model=TranscriptionResponse)
async def transcribe_voice(
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
    Voice / audio → natural language text (speech-to-text).

    Uses OpenAI Whisper or Groq Whisper. With SPEECH_PROVIDER=auto (default),
    picks OpenAI when OPENAI_API_KEY is set, otherwise Groq.
    """
    transcription_id = str(uuid.uuid4())
    suffix = Path(audio.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type '{suffix}'. Allowed: {sorted(ALLOWED_AUDIO)}",
        )

    audio_dir = settings().audio_root / transcription_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"input{suffix}"

    await _save_upload(audio, audio_path, allowed_suffixes=ALLOWED_AUDIO)

    try:
        result = transcribe_audio(audio_path, language=language, provider=provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc

    get_store().save_transcription(
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


@router.get("/audio/transcriptions/{transcription_id}")
def get_transcription(transcription_id: str) -> dict[str, Any]:
    try:
        return get_store().get_transcription(transcription_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/voice/contract", response_model=VoiceContractResponse)
def voice_contract_from_text(body: VoiceContractRequest) -> VoiceContractResponse:
    """
    Start LangGraph voice-contract agent.
    Returns needs_confirmation + thread_id for HITL resume, unless auto_create=true.
    """
    store = get_store()
    result = run_voice_contract_workflow(
        body.transcript,
        store=store,
        auto_create=body.auto_create,
    )
    payload = result.to_dict()
    if result.ok and result.status == "completed":
        saved = _persist_voice_contract(store, result)
        payload["contract_id"] = saved["contract_id"]
        payload["contract_file"] = saved.get("contract_file")
        payload["contract_text_file"] = saved.get("contract_text_file") or result.contract_text_file
        payload["message"] = (
            f"{result.message} Saved to SQLite as contract `{saved['contract_id']}`."
        )
    return VoiceContractResponse(**payload)


@router.post("/voice/contract/confirm", response_model=VoiceContractResponse)
def voice_contract_confirm(body: VoiceContractConfirmRequest) -> VoiceContractResponse:
    """Resume LangGraph HITL interrupt (preferred) or finalize by entity/ref."""
    store = get_store()
    result = confirm_voice_contract(
        entity_code_or_name=body.legal_entity,
        contract_reference_number=body.contract_reference_number,
        store=store,
        transcript=body.transcript,
        thread_id=body.thread_id,
        user_text=body.user_text or "yes",
    )
    payload = result.to_dict()
    if result.ok and result.status == "completed":
        # Always normalize draft files into storage + ensure SQLite row exists.
        saved = _persist_voice_contract(store, result)
        payload["contract_id"] = saved["contract_id"]
        payload["contract_file"] = saved.get("contract_file")
        payload["contract_text_file"] = saved.get("contract_text_file") or result.contract_text_file
        payload["message"] = (
            f"{result.message} Saved to SQLite as contract `{saved['contract_id']}`."
        )
    return VoiceContractResponse(**payload)


@router.post("/voice/contract/from-audio", response_model=VoiceContractResponse)
async def voice_contract_from_audio(
    audio: UploadFile = File(..., description="Audio file (mp3, wav, m4a, webm, …)"),
    language: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    auto_create: bool = Form(default=False),
) -> VoiceContractResponse:
    """Transcribe audio, then parse create-contract (confirmation by default)."""
    transcription_id = str(uuid.uuid4())
    suffix = Path(audio.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type '{suffix}'. Allowed: {sorted(ALLOWED_AUDIO)}",
        )

    audio_dir = settings().audio_root / transcription_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"input{suffix}"
    await _save_upload(audio, audio_path, allowed_suffixes=ALLOWED_AUDIO)

    try:
        transcription = transcribe_audio(audio_path, language=language, provider=provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc

    store = get_store()
    store.save_transcription(
        transcription_id,
        audio_path,
        transcription.text,
        transcription.provider,
        transcription.model,
    )

    result = run_voice_contract_workflow(
        transcription.text,
        store=store,
        auto_create=auto_create,
    )
    payload = result.to_dict()
    payload["transcription_id"] = transcription_id
    payload["provider"] = transcription.provider
    payload["model"] = transcription.model
    if result.ok and result.status == "completed":
        saved = _persist_voice_contract(
            store,
            result,
            transcription_id=transcription_id,
        )
        payload["contract_id"] = saved["contract_id"]
        payload["contract_file"] = saved.get("contract_file")
        payload["contract_text_file"] = saved.get("contract_text_file") or result.contract_text_file
        payload["message"] = (
            f"{result.message} Saved to SQLite as contract `{saved['contract_id']}`."
        )
    return VoiceContractResponse(**payload)


def _persist_voice_contract(
    store: Any,
    result: Any,
    *,
    transcription_id: str | None = None,
) -> dict[str, Any]:
    import shutil

    contract_id = str(uuid.uuid4())
    final_docx: str | None = None
    final_txt: str | None = None
    dest_dir = settings().storage_base_path / "voice_contracts"
    dest_dir.mkdir(parents=True, exist_ok=True)

    if result.contract_file:
        src = Path(result.contract_file)
        dest = dest_dir / f"{contract_id}.docx"
        if src.exists():
            shutil.move(str(src), str(dest))
            final_docx = str(dest)
    if result.contract_text_file:
        src_txt = Path(result.contract_text_file)
        dest_txt = dest_dir / f"{contract_id}.txt"
        if src_txt.exists():
            shutil.move(str(src_txt), str(dest_txt))
            final_txt = str(dest_txt)
    elif result.contract_text:
        dest_txt = dest_dir / f"{contract_id}.txt"
        dest_txt.write_text(result.contract_text, encoding="utf-8")
        final_txt = str(dest_txt)

    saved = store.save_voice_contract(
        contract_id=contract_id,
        spoken_name=result.spoken_name or result.legal_entity_name or "",
        spoken_number=result.spoken_number or result.contract_reference_number or "",
        contact=result.contact or result.legal_entity,
        legal_entity=result.legal_entity,
        pricelist=result.pricelist,
        contract_payload=result.contract_payload,
        contract_file=final_docx or final_txt,
        transcript=result.transcript,
        transcription_id=transcription_id,
    )
    saved["contract_text_file"] = final_txt
    return saved


@router.get("/voice/contracts/{contract_id}")
def get_voice_contract(contract_id: str) -> dict[str, Any]:
    try:
        return get_store().get_voice_contract(contract_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/voice/contracts/{contract_id}/download")
def download_voice_contract(contract_id: str, format: str = "docx") -> FileResponse:
    try:
        row = get_store().get_voice_contract(contract_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = row.get("contract_file")
    if format.lower() == "txt":
        # Prefer sibling .txt next to stored file
        if path:
            txt_candidate = Path(path).with_suffix(".txt")
            if txt_candidate.is_file():
                path = str(txt_candidate)
        if not path or not str(path).endswith(".txt"):
            payload = row.get("contract_payload") or {}
            if payload:
                from document_processing_agenticflow.services.voice_contract_workflow import (
                    render_contract_text,
                )

                tmp = settings().storage_base_path / "voice_contracts" / f"{contract_id}.txt"
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


@router.get("/voice/contracts")
def list_voice_contracts(limit: int = 50) -> dict[str, Any]:
    rows = get_store().list_voice_contracts(limit=limit)
    return {"count": len(rows), "contracts": rows}
