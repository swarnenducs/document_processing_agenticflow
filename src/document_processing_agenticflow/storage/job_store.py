"""SQLite job metadata + configurable filesystem paths for document blobs."""

from __future__ import annotations

import json
import re
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_contracts (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    spoken_name TEXT NOT NULL,
                    spoken_number TEXT NOT NULL,
                    contact_name TEXT,
                    contact_json TEXT,
                    legal_entity_json TEXT,
                    pricelist_json TEXT,
                    contract_payload_json TEXT,
                    contract_file TEXT,
                    transcript TEXT,
                    transcription_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS legal_entities (
                    code TEXT PRIMARY KEY,
                    legal_name TEXT NOT NULL,
                    address TEXT,
                    city TEXT,
                    country TEXT,
                    postal_code TEXT,
                    email TEXT,
                    phone TEXT,
                    registration_number TEXT,
                    entity_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pricelists (
                    contract_reference_number TEXT PRIMARY KEY,
                    legal_entity_code TEXT NOT NULL,
                    currency TEXT,
                    effective_date TEXT,
                    pricelist_json TEXT NOT NULL
                )
                """
            )
            # Backward-compatible columns if an older voice_contracts table exists
            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(voice_contracts)").fetchall()
            }
            for col, typ in (
                ("legal_entity_json", "TEXT"),
                ("pricelist_json", "TEXT"),
                ("contract_payload_json", "TEXT"),
                ("contract_file", "TEXT"),
            ):
                if col not in existing:
                    conn.execute(f"ALTER TABLE voice_contracts ADD COLUMN {col} {typ}")

    def create_job_paths(
        self,
        job_id: str | None = None,
        *,
        template_filename: str | None = None,
    ) -> tuple[str, Path, Path, Path, Path]:
        """Return (job_id, job_dir, template_path, data_path, output_path).

        Output file is named ``{job_id_last_block}_{template_stem}.docx``.
        """
        from document_processing_agenticflow.services.naming import build_contract_output_filename

        jid = job_id or str(uuid.uuid4())
        job_dir = self.cfg.job_dir(jid)
        job_dir.mkdir(parents=True, exist_ok=True)
        template_path = job_dir / "template.docx"
        data_path = job_dir / "data.json"
        output_name = build_contract_output_filename(
            jid, template_filename or "template.docx"
        )
        output_path = job_dir / output_name
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

    def save_voice_contract(
        self,
        *,
        spoken_name: str,
        spoken_number: str,
        contact: dict[str, Any] | None = None,
        legal_entity: dict[str, Any] | None = None,
        pricelist: dict[str, Any] | None = None,
        contract_payload: dict[str, Any] | None = None,
        contract_file: str | None = None,
        transcript: str | None = None,
        transcription_id: str | None = None,
        contract_id: str | None = None,
        status: str = "accepted",
    ) -> dict[str, Any]:
        """Persist an accepted voice create-contract request in SQLite."""
        cid = contract_id or str(uuid.uuid4())
        now = _now_iso()
        entity = legal_entity or contact
        contact_name = None
        if entity:
            contact_name = str(
                entity.get("legalName") or entity.get("name") or entity.get("code") or ""
            ) or None

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO voice_contracts (
                    id, status, spoken_name, spoken_number, contact_name,
                    contact_json, legal_entity_json, pricelist_json,
                    contract_payload_json, contract_file, transcript,
                    transcription_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    status,
                    spoken_name,
                    spoken_number,
                    contact_name,
                    json.dumps(entity) if entity else None,
                    json.dumps(legal_entity) if legal_entity else None,
                    json.dumps(pricelist) if pricelist else None,
                    json.dumps(contract_payload) if contract_payload else None,
                    contract_file,
                    transcript,
                    transcription_id,
                    now,
                ),
            )
        return self.get_voice_contract(cid)

    def get_voice_contract(self, contract_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM voice_contracts WHERE id = ?", (contract_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Voice contract not found: {contract_id}")
        data = dict(row)
        for src, dst in (
            ("contact_json", "contact"),
            ("legal_entity_json", "legal_entity"),
            ("pricelist_json", "pricelist"),
            ("contract_payload_json", "contract_payload"),
        ):
            raw = data.get(src)
            data[dst] = json.loads(raw) if raw else None
        data["contract_id"] = data.pop("id")
        return data

    def list_voice_contracts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM voice_contracts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            for src, dst in (
                ("contact_json", "contact"),
                ("legal_entity_json", "legal_entity"),
                ("pricelist_json", "pricelist"),
                ("contract_payload_json", "contract_payload"),
            ):
                raw = data.get(src)
                data[dst] = json.loads(raw) if raw else None
            data["contract_id"] = data.pop("id")
            out.append(data)
        return out

    def ensure_contract_catalog_seeded(self) -> None:
        """Load sample legal entities + pricelists into SQLite once."""
        catalog_path = (
            Path(__file__).resolve().parents[3]
            / "samples"
            / "data"
            / "contract_catalog.json"
        )
        with self._conn() as conn:
            entity_count = conn.execute("SELECT COUNT(*) FROM legal_entities").fetchone()[0]
            list_count = conn.execute("SELECT COUNT(*) FROM pricelists").fetchone()[0]
            if entity_count and list_count:
                return
            if not catalog_path.is_file():
                return
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            for entity in payload.get("legal_entities") or []:
                if not isinstance(entity, dict):
                    continue
                code = str(entity.get("code") or "").strip()
                if not code:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO legal_entities (
                        code, legal_name, address, city, country, postal_code,
                        email, phone, registration_number, entity_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        str(entity.get("legalName") or code),
                        entity.get("address"),
                        entity.get("city"),
                        entity.get("country"),
                        entity.get("postalCode"),
                        entity.get("email"),
                        entity.get("phone"),
                        entity.get("registrationNumber"),
                        json.dumps(entity),
                    ),
                )
            for pricelist in payload.get("pricelists") or []:
                if not isinstance(pricelist, dict):
                    continue
                ref = str(pricelist.get("contractReferenceNumber") or "").strip()
                if not ref:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pricelists (
                        contract_reference_number, legal_entity_code, currency,
                        effective_date, pricelist_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        ref,
                        str(pricelist.get("legalEntityCode") or ""),
                        pricelist.get("currency"),
                        pricelist.get("effectiveDate"),
                        json.dumps(pricelist),
                    ),
                )

    def find_legal_entity(self, name_or_code: str) -> dict[str, Any] | None:
        needle = " ".join((name_or_code or "").lower().split())
        if not needle:
            return None
        self.ensure_contract_catalog_seeded()
        with self._conn() as conn:
            rows = conn.execute("SELECT entity_json FROM legal_entities").fetchall()
        exact: dict[str, Any] | None = None
        partial: dict[str, Any] | None = None
        for row in rows:
            entity = json.loads(row["entity_json"])
            candidates = [
                str(entity.get("code") or "").lower(),
                str(entity.get("legalName") or "").lower(),
            ]
            if any(c == needle for c in candidates if c):
                exact = entity
                break
            if any(needle in c or c in needle for c in candidates if c):
                partial = partial or entity
        return exact or partial

    def find_pricelist(self, contract_reference_number: str) -> dict[str, Any] | None:
        matches = self.search_pricelists(contract_reference_number)
        return matches[0] if matches else None

    def search_pricelists(
        self,
        contract_reference_number: str,
        *,
        legal_entity_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fuzzy match contract refs ('CR 1001' ≈ 'CR-1001')."""
        needle = re.sub(r"[\s\-_]+", "", (contract_reference_number or "").upper())
        if not needle:
            return []
        self.ensure_contract_catalog_seeded()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT contract_reference_number, legal_entity_code, pricelist_json "
                "FROM pricelists"
            ).fetchall()

        scored: list[tuple[int, dict[str, Any]]] = []
        wanted_code = (legal_entity_code or "").strip().upper() or None
        for row in rows:
            ref = str(row["contract_reference_number"] or "")
            compact = re.sub(r"[\s\-_]+", "", ref.upper())
            code = str(row["legal_entity_code"] or "").upper()
            if wanted_code and code and code != wanted_code:
                continue
            score = 0
            if compact == needle:
                score = 100
            elif needle in compact or compact in needle:
                score = 80
            elif compact.startswith(needle) or needle.startswith(compact):
                score = 60
            if score:
                scored.append((score, json.loads(row["pricelist_json"])))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]
