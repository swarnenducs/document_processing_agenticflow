"""SQLAlchemy models for voice contract + call-log rows (same tables as ip_api)."""

from __future__ import annotations

from sqlalchemy import Float, Index, Integer, LargeBinary, Unicode, UnicodeText
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    """xid-correlated HTTP / tool / LLM trace rows."""

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


class LgCheckpoint(Base):
    """LangGraph HITL snapshot (thread_id + namespace + checkpoint id)."""

    __tablename__ = "lg_checkpoints"

    thread_id: Mapped[str] = mapped_column(Unicode(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Unicode(256), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Unicode(128), primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(Unicode(128), nullable=True)
    checkpoint_type: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    checkpoint_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    metadata_type: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    metadata_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (Index("idx_lg_checkpoints_thread", "thread_id"),)


class LgCheckpointBlob(Base):
    """Channel value blobs for a checkpoint version."""

    __tablename__ = "lg_checkpoint_blobs"

    thread_id: Mapped[str] = mapped_column(Unicode(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Unicode(256), primary_key=True, default="")
    channel: Mapped[str] = mapped_column(Unicode(256), primary_key=True)
    version: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    blob_type: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    __table_args__ = (Index("idx_lg_checkpoint_blobs_thread", "thread_id"),)


class LgCheckpointWrite(Base):
    """Pending channel writes attached to a checkpoint (interrupts, resumes)."""

    __tablename__ = "lg_checkpoint_writes"

    thread_id: Mapped[str] = mapped_column(Unicode(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Unicode(256), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Unicode(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(Unicode(128), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(Unicode(256), nullable=False)
    blob_type: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    task_path: Mapped[str] = mapped_column(Unicode(512), nullable=False, default="")

    __table_args__ = (Index("idx_lg_checkpoint_writes_thread", "thread_id"),)
