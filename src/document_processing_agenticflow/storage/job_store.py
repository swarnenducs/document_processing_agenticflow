"""SQLite job metadata + configurable filesystem paths for document blobs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from document_processing_agenticflow.core.settings import settings


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JobRecord:
    id: str
    status: str
    template_path: str
    data_path: str
    output_path: str | None
    error_message: str | None
    confidence_json: str | None
    validation_json: str | None
    mapper_llm: str | None
    validator_llm: str | None
    created_at: str
    updated_at: str
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.id,
            "status": self.status,
            "template_path": self.template_path,
            "data_path": self.data_path,
            "output_path": self.output_path,
            "error_message": self.error_message,
            "mapper_llm": self.mapper_llm,
            "validator_llm": self.validator_llm,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }
        if self.confidence_json:
            out["confidence"] = json.loads(self.confidence_json)
        if self.validation_json:
            out["validation"] = json.loads(self.validation_json)
        return out


class JobStore:
    """Persist job metadata in SQLite; blobs live on disk under STORAGE_BASE_PATH."""

    def __init__(self, db_path: Path | None = None) -> None:
        cfg = settings()
        self.db_path = db_path or cfg.sqlite_database_path
        self.cfg = cfg
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    template_path TEXT NOT NULL,
                    data_path TEXT NOT NULL,
                    output_path TEXT,
                    error_message TEXT,
                    confidence_json TEXT,
                    validation_json TEXT,
                    mapper_llm TEXT,
                    validator_llm TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcription_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    transcript TEXT,
                    provider TEXT,
                    model TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

    def create_job_paths(self, job_id: str | None = None) -> tuple[str, Path, Path, Path, Path]:
        """Return (job_id, job_dir, template_path, data_path, output_path)."""
        jid = job_id or str(uuid.uuid4())
        job_dir = self.cfg.job_dir(jid)
        job_dir.mkdir(parents=True, exist_ok=True)
        template_path = job_dir / "template.docx"
        data_path = job_dir / "data.json"
        output_path = job_dir / "output.docx"
        return jid, job_dir, template_path, data_path, output_path

    def insert_job(
        self,
        job_id: str,
        template_path: Path,
        data_path: Path,
        output_path: Path,
    ) -> JobRecord:
        now = _now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO document_jobs (
                    id, status, template_path, data_path, output_path,
                    error_message, confidence_json, validation_json,
                    mapper_llm, validator_llm, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, NULL)
                """,
                (
                    job_id,
                    "pending",
                    str(template_path),
                    str(data_path),
                    str(output_path),
                    now,
                    now,
                ),
            )
        return self.get_job(job_id)

    def update_status(self, job_id: str, status: str, error: str | None = None) -> None:
        now = _now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE document_jobs
                SET status = ?, updated_at = ?, error_message = COALESCE(?, error_message)
                WHERE id = ?
                """,
                (status, now, error, job_id),
            )

    def complete_job(
        self,
        job_id: str,
        *,
        confidence: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        mapper_llm: str | None = None,
        validator_llm: str | None = None,
        error: str | None = None,
    ) -> None:
        now = _now_iso()
        status = "failed" if error else "completed"
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE document_jobs SET
                    status = ?,
                    updated_at = ?,
                    completed_at = ?,
                    error_message = ?,
                    confidence_json = ?,
                    validation_json = ?,
                    mapper_llm = ?,
                    validator_llm = ?
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    now,
                    error,
                    json.dumps(confidence) if confidence else None,
                    json.dumps(validation) if validation else None,
                    mapper_llm,
                    validator_llm,
                    job_id,
                ),
            )

    def get_job(self, job_id: str) -> JobRecord:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM document_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return JobRecord(**dict(row))

    def delete_job(self, job_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM document_jobs WHERE id = ?", (job_id,))
        job_dir = self.cfg.job_dir(job_id)
        if job_dir.exists():
            for p in job_dir.iterdir():
                p.unlink(missing_ok=True)
            job_dir.rmdir()

    def save_transcription(
        self,
        transcription_id: str,
        audio_path: Path,
        transcript: str,
        provider: str,
        model: str,
    ) -> None:
        now = _now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO transcription_jobs (
                    id, status, audio_path, transcript, provider, model,
                    error_message, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    transcription_id,
                    "completed",
                    str(audio_path),
                    transcript,
                    provider,
                    model,
                    now,
                    now,
                ),
            )

    def get_transcription(self, transcription_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM transcription_jobs WHERE id = ?", (transcription_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Transcription not found: {transcription_id}")
        return dict(row)
