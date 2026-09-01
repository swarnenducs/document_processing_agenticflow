"""Pydantic schemas for FastAPI request/response bodies."""

from __future__ import annotations

from typing import Any, Literal, Literal

from pydantic import BaseModel, ConfigDict, Field


class JobCreateOptions(BaseModel):
    skip_validation: bool = False
    max_retries: int | None = Field(default=None, ge=0, le=3)
    validation_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    optimized_flow: bool = False


class JobAcceptedResponse(BaseModel):
    job_id: str = Field(description="Use in status, download, WebSocket, and accuracy URLs")
    xid: str | None = Field(default=None, description="Correlation id (also in X-Request-ID)")
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    status: Literal["pending", "processing"] = "pending"
    message: str = (
        "Job accepted. Prefer WebSocket ws_url for live stages, "
        "or long-poll GET status_url?wait=true, then download."
    )
    status_url: str = Field(description="GET this path; add ?wait=true to long-poll")
    download_url: str = Field(description="GET when status is completed")
    ws_url: str | None = Field(default=None, description="WebSocket for live stages")


class JobStatusResponse(BaseModel):
    job_id: str
    mcp: str | None = Field(default=None, description="Which MCP handled the job, when known")
    xid: str | None = None
    session_id: str | None = None
    status: str = Field(description="pending | processing | completed | failed")
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
    elapsed_ms: float | None = None
    elapsed: str | None = None
    download_url: str | None = None
    accuracy_pdf_url: str | None = Field(
        default=None,
        description="GET this path for the accuracy report PDF",
    )
    sqlite_persisted: bool = True
    accuracy_report: dict[str, Any] | None = None


class JobListResponse(BaseModel):
    count: int
    jobs: list[JobStatusResponse]


class TemplateRecordResponse(BaseModel):
    """One Word template in the default library folder."""

    folder_name: str
    template_name: str
    location: str = Field(description="Library path: folder_name/template_name")
    storage_backend: Literal["local", "azure_blob"]
    storage_ref: str = Field(description="Local absolute path or blob:// reference")
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    uploaded_by: str | None = None
    created_at: str
    updated_at: str
    download_url: str | None = None


class LibraryTemplateItem(BaseModel):
    folder_name: str
    template_name: str
    location: str
    storage_backend: Literal["local", "azure_blob"]


class LibraryTemplateListResponse(BaseModel):
    folder_name: str
    count: int
    storage_backend: str
    templates: list[LibraryTemplateItem]


class TemplateListResponse(BaseModel):
    count: int
    storage_backend: Literal["local", "azure_blob"]
    templates: list[TemplateRecordResponse]


class TemplateDeletedResponse(BaseModel):
    deleted: bool = True
    folder_name: str
    template_name: str
    location: str


class MasterDataUpsertRequest(BaseModel):
    placeholder_key: str = Field(
        description="Template token without brackets, e.g. Legal_Department_Master_Data"
    )
    content: str = Field(description="Block text written into the Word placeholder")
    category: str | None = Field(
        default=None,
        description="legal | sales | general. Inferred from the key when omitted.",
    )
    active: bool = Field(default=True, description="Inactive rows are ignored by document MCP")


class MasterDataUpdateRequest(BaseModel):
    content: str = Field(description="Block text written into the Word placeholder")
    category: str | None = Field(default=None)
    active: bool = Field(default=True)


class MasterDataRecordResponse(BaseModel):
    id: str
    placeholder_key: str
    category: str
    content: str
    active: bool
    updated_at: str


class MasterDataListResponse(BaseModel):
    count: int
    items: list[MasterDataRecordResponse]


class MasterDataDeletedResponse(BaseModel):
    deleted: bool = True
    placeholder_key: str


class AdminTokenRequest(BaseModel):
    admin_key: str | None = Field(
        default=None,
        description="Required when env ADMIN_API_KEY is set. Same value as X-Admin-Api-Key.",
    )
    ttl_seconds: int | None = Field(
        default=None,
        ge=60,
        le=604800,
        description="Override ADMIN_TOKEN_TTL_SECONDS (60 seconds – 7 days).",
    )


class AdminTokenResponse(BaseModel):
    access_token: str = Field(description="PyJWT HS256 compact token")
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = Field(description="Seconds until exp")
    expires_at: str = Field(description="UTC ISO-8601 expiry")
    token_header: str = Field(
        default="Authorization: Bearer <access_token>  or  X-Admin-Api-Key: <access_token>",
        description="How to send the token on later admin calls",
    )


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
    """Start HITL from already-transcribed (or typed) text."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transcript": (
                    "please create contract with legal entity AVC "
                    "contract reference number CR-1001"
                ),
                "auto_create": False,
            }
        }
    )

    transcript: str = Field(..., min_length=1, description="Spoken / typed instruction")
    auto_create: bool = Field(
        default=False,
        description="If true, skip human confirmation and create immediately",
    )
    session_id: str | None = Field(default=None, description="Reuse client session id")
    user_id: str | None = None
    user_email: str | None = None


class VoiceContractConfirmRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "legal_entity": "AVC",
                "contract_reference_number": "CR-1001",
                "thread_id": "paste-thread-id-from-start",
                "user_text": "yes",
            }
        }
    )

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
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None


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
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="ok if mapper LLM is configured, else degraded")
    storage_base_path: str = Field(description="Local storage root used by this gateway")
    sqlite_database_path: str = Field(description="SQLite file when not on Azure SQL")
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
    # Central agent (MAF) — standalone :8003 or embedded
    maf_available: bool = False
    maf_mode: str | None = None
    maf_base_url: str | None = None
    storage_backend: str | None = None
    azure_sql_server: str | None = None
    azure_sql_database: str | None = None
    azure_blob_container: str | None = None
    azure_sql_available: bool | None = None
    azure_blob_available: bool | None = None
