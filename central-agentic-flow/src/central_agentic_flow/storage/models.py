"""SQLAlchemy model for MAF call-log rows (same table as ip_api)."""

from __future__ import annotations

from sqlalchemy import Float, Index, Unicode, UnicodeText
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
