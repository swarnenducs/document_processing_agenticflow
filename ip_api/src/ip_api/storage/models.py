"""SQLAlchemy ORM models for document-processing metadata."""

from __future__ import annotations

from sqlalchemy import Float, Index, Unicode, UnicodeText
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOCUMENT_MCP = "document_process_mcp"
JOB_TABLE_DOCUMENT_MCP = "job_table_document_mcp"
ACCURACY_TABLE_DOCUMENT_MCP = "accuracy_report_document_mcp"


class Base(DeclarativeBase):
    pass


class DocumentJob(Base):
    __tablename__ = JOB_TABLE_DOCUMENT_MCP

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    mcp: Mapped[str] = mapped_column(Unicode(64), nullable=False, default=DOCUMENT_MCP)
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False)
    template_path: Mapped[str] = mapped_column(Unicode(1024), nullable=False)
    data_path: Mapped[str] = mapped_column(Unicode(1024), nullable=False)
    output_path: Mapped[str | None] = mapped_column(Unicode(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    confidence_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    validation_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    mapper_llm: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    validator_llm: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    extraction_validation_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    result_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    xid: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)

    __table_args__ = (Index("idx_job_table_document_mcp_xid", "xid"),)


class DocumentAccuracyReport(Base):
    """Per-job accuracy / confidence report (document processing)."""

    __tablename__ = ACCURACY_TABLE_DOCUMENT_MCP

    job_id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    mcp: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    xid: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    overall_confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    mapping_confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    table_mapping_confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_integrity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_score_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_passed: Mapped[str | None] = mapped_column(Unicode(8), nullable=True)
    validation_passed: Mapped[str | None] = mapped_column(Unicode(8), nullable=True)
    mapper_llm: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    validator_llm: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    notes: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    confidence_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    validation_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    extraction_validation_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    scores_pct_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False)
    audio_path: Mapped[str] = mapped_column(Unicode(1024), nullable=False)
    transcript: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    provider: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    model: Mapped[str | None] = mapped_column(Unicode(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)


class VoiceContract(Base):
    __tablename__ = "voice_contracts"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False)
    spoken_name: Mapped[str] = mapped_column(Unicode(256), nullable=False)
    spoken_number: Mapped[str] = mapped_column(Unicode(128), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    contact_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    legal_entity_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    pricelist_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    contract_payload_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    contract_file: Mapped[str | None] = mapped_column(Unicode(1024), nullable=True)
    transcript: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    transcription_id: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    xid: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    job_id: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    kind: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(512), nullable=False)
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    model: Mapped[str | None] = mapped_column(Unicode(128), nullable=True)
    request_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    response_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    error_message: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)

    __table_args__ = (
        Index("idx_call_logs_xid", "xid"),
        Index("idx_call_logs_job_id", "job_id"),
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Unicode(128), nullable=True)
    user_email: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    last_request_kind: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    last_xid: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    meta_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

    __table_args__ = (Index("idx_sessions_user_id", "user_id"),)


class SessionRequest(Base):
    __tablename__ = "session_requests"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    xid: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    request_kind: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    path: Mapped[str | None] = mapped_column(Unicode(512), nullable=True)
    created_at: Mapped[str] = mapped_column(Unicode(64), nullable=False)

    __table_args__ = (Index("idx_session_requests_session", "session_id"),)
