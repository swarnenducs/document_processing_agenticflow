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
    status: Literal["pending", "processing"] = "pending"
    message: str = "Job accepted. Poll status or download when completed."
    status_url: str
    download_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    template_path: str | None = None
    output_path: str | None = None
    error_message: str | None = None
    mapper_llm: str | None = None
    validator_llm: str | None = None
    confidence: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    # All scores in % for UI clients
    scores_pct: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    download_url: str | None = None


class TranscriptionResponse(BaseModel):
    transcription_id: str
    text: str
    provider: str
    model: str
    language: str | None = None


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
