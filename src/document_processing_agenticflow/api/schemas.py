"""Pydantic schemas for FastAPI request/response bodies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JobCreateOptions(BaseModel):
    skip_validation: bool = False
    max_retries: int = Field(default=1, ge=0, le=3)
    validation_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class JobAcceptedResponse(BaseModel):
    job_id: str
    xid: str | None = None
    status: Literal["pending", "processing"] = "pending"
    message: str = (
        "Job accepted. Prefer WebSocket ws_url for live stages, "
        "or long-poll GET status_url?wait=true, then download."
    )
    status_url: str
    download_url: str
    ws_url: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    xid: str | None = None
    status: str
    template_path: str | None = None
    output_path: str | None = None
    error_message: str | None = None
    mapper_llm: str | None = None
    validator_llm: str | None = None
    confidence: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    extraction_validation: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    # All scores in % for UI clients
    scores_pct: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    download_url: str | None = None
    sqlite_persisted: bool = True


class JobListResponse(BaseModel):
    count: int
    jobs: list[JobStatusResponse]


class TraceByXidResponse(BaseModel):
    xid: str
    job_count: int
    log_count: int
    jobs: list[dict[str, Any]]
    logs: list[dict[str, Any]]


class TranscriptionResponse(BaseModel):
    transcription_id: str
    text: str
    provider: str
    model: str
    language: str | None = None


class VoiceContractRequest(BaseModel):
    """Optional: run workflow on already-transcribed text (no audio)."""

    transcript: str = Field(..., min_length=1, description="Spoken / typed instruction")
    auto_create: bool = Field(
        default=False,
        description="If true, skip human confirmation and create immediately",
    )


class VoiceContractConfirmRequest(BaseModel):
    legal_entity: str = Field(..., min_length=1, description="Legal entity code or name")
    contract_reference_number: str = Field(
        ..., min_length=1, description="Contract reference to confirm, e.g. CR-1001"
    )
    transcript: str | None = None
    thread_id: str | None = Field(
        default=None,
        description="LangGraph thread id from needs_confirmation response (HITL resume)",
    )
    user_text: str | None = Field(
        default=None,
        description="Raw user reply such as yes / CR-1001",
    )


class VoiceContractResponse(BaseModel):
    ok: bool
    message: str
    intent: str | None = None
    status: str | None = None
    legal_entity_name: str | None = None
    contract_reference_number: str | None = None
    legal_entity: dict[str, Any] | None = None
    pricelist: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] | None = None
    contract_payload: dict[str, Any] | None = None
    contract_file: str | None = None
    contract_text_file: str | None = None
    contract_text: str | None = None
    spoken_name: str | None = None
    spoken_number: str | None = None
    contact: dict[str, Any] | None = None
    transcript: str | None = None
    contract_id: str | None = None
    thread_id: str | None = None
    transcription_id: str | None = None
    provider: str | None = None
    model: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    storage_base_path: str
    sqlite_database_path: str
    speech_provider: str
    # LLM availability for UI banners (no secrets)
    mapper_provider: str | None = None
    mapper_model: str | None = None
    mapper_available: bool = False
    validator_provider: str | None = None
    validator_model: str | None = None
    validator_available: bool = False
    speech_available: bool = False
    # Separate FastMCP servers (HTTP)
    document_mcp_available: bool = False
    voice_mcp_available: bool = False
