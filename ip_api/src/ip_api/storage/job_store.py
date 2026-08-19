"""SQLAlchemy job metadata + Azure Blob (or local disk) for document blobs."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ip_api.core.settings import settings
from ip_api.storage.blob_store import blob_job_root, get_blob_store, is_blob_ref
from ip_api.storage.db import ensure_schema, get_session_factory
from ip_api.storage.models import (
    CallLog,
    DOCUMENT_MCP,
    DocumentAccuracyReport,
    DocumentJob,
    TranscriptionJob,
    VoiceContract,
)


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
    extraction_validation_json: str | None = None
    result_json: str | None = None
    xid: str | None = None
    elapsed_ms: float | None = None
    elapsed: str | None = None
    mcp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.id,
            "mcp": self.mcp,
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
            "xid": self.xid,
            "elapsed_ms": self.elapsed_ms,
            "elapsed": self.elapsed,
        }
        if self.confidence_json:
            out["confidence"] = json.loads(self.confidence_json)
        if self.validation_json:
            out["validation"] = json.loads(self.validation_json)
        if self.extraction_validation_json:
            out["extraction_validation"] = json.loads(self.extraction_validation_json)
        if self.result_json:
            out["result"] = json.loads(self.result_json)
        return out


def _job_to_record(row: DocumentJob) -> JobRecord:
    return JobRecord(
        id=row.id,
        status=row.status,
        template_path=row.template_path,
        data_path=row.data_path,
        output_path=row.output_path,
        error_message=row.error_message,
        confidence_json=row.confidence_json,
        validation_json=row.validation_json,
        mapper_llm=row.mapper_llm,
        validator_llm=row.validator_llm,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        extraction_validation_json=row.extraction_validation_json,
        result_json=row.result_json,
        xid=row.xid,
        elapsed_ms=getattr(row, "elapsed_ms", None),
        elapsed=getattr(row, "elapsed", None),
        mcp=getattr(row, "mcp", None),
    )


class JobStore:
    """Persist job metadata via SQLAlchemy (Azure SQL or SQLite); files in Blob or disk."""

    def __init__(self, db_path: Path | None = None) -> None:
        cfg = settings()
        self.db_path = db_path or cfg.sqlite_database_path
        self.cfg = cfg
        self._sqlite_override = db_path
        ensure_schema(sqlite_path=db_path)
        self._session_factory = get_session_factory(sqlite_path=db_path)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def create_job_paths(
        self,
        job_id: str | None = None,
        *,
        template_filename: str | None = None,
    ) -> tuple[str, Path, Path, Path, Path]:
        """Return (job_id, job_dir, template_path, data_path, output_path).

        Local scratch paths are always created so uploads can be staged before Blob.
        """
        from ip_api.services.naming import build_contract_output_filename

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
        template_path: Path | str,
        data_path: Path | str,
        output_path: Path | str,
        *,
        xid: str | None = None,
    ) -> JobRecord:
        blobs = get_blob_store()
        tpl = Path(template_path)
        data = Path(data_path)
        out = Path(output_path)
        stored_tpl, stored_data, stored_out = blobs.persist_job_inputs(job_id, tpl, data, out)
        now = _now_iso()
        with self._session() as session:
            session.add(
                DocumentJob(
                    id=job_id,
                    mcp=DOCUMENT_MCP,
                    status="pending",
                    template_path=stored_tpl,
                    data_path=stored_data,
                    output_path=stored_out,
                    created_at=now,
                    updated_at=now,
                    xid=xid,
                )
            )
        return self.get_job(job_id)

    def materialize_job_files(self, job: JobRecord) -> tuple[Path, Path, Path]:
        """Open local template + JSON; output is written locally then uploaded to Blob."""
        job_dir = self.cfg.job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        blobs = get_blob_store()

        def _local(ref: str, filename: str) -> Path:
            dest = job_dir / filename
            if is_blob_ref(ref) and blobs.enabled:
                return blobs.download_file(ref, dest)
            src = Path(ref)
            if src.exists():
                if src.resolve() != dest.resolve():
                    dest.write_bytes(src.read_bytes())
                return dest
            if dest.exists():
                return dest
            raise FileNotFoundError(f"Job file not found: {ref}")

        template_name = "template.docx"
        data_name = "data.json"
        output_name = Path(job.output_path or "output.docx").name
        template_path = _local(job.template_path, template_name)
        data_path = _local(job.data_path, data_name)
        output_path = job_dir / output_name
        if job.output_path and not is_blob_ref(job.output_path) and Path(job.output_path).exists():
            output_path = Path(job.output_path)
        return template_path, data_path, output_path

    def persist_output(self, job_id: str, output_path: Path) -> str:
        ref = get_blob_store().persist_job_output(job_id, output_path)
        with self._session() as session:
            row = session.get(DocumentJob, job_id)
            if row is not None:
                row.output_path = ref
                row.updated_at = _now_iso()
        return ref

    def resolve_output_file(self, job: JobRecord) -> Path:
        if job.output_path and Path(job.output_path).exists() and not is_blob_ref(job.output_path):
            return Path(job.output_path)
        dest = self.cfg.job_dir(job.id) / Path(job.output_path or "output.docx").name
        if dest.exists():
            return dest
        blobs = get_blob_store()
        if job.output_path and blobs.enabled:
            return blobs.download_file(job.output_path, dest)
        raise FileNotFoundError("Output file not found")

    def update_status(self, job_id: str, status: str, error: str | None = None) -> None:
        now = _now_iso()
        with self._session() as session:
            row = session.get(DocumentJob, job_id)
            if row is None:
                return
            row.status = status
            row.updated_at = now
            if error:
                row.error_message = error

    def complete_job(
        self,
        job_id: str,
        *,
        confidence: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        extraction_validation: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        mapper_llm: str | None = None,
        validator_llm: str | None = None,
        error: str | None = None,
        output_path: str | None = None,
    ) -> None:
        now = _now_iso()
        status = "failed" if error else "completed"
        with self._session() as session:
            row = session.get(DocumentJob, job_id)
            if row is None:
                return
            row.status = status
            row.updated_at = now
            row.completed_at = now
            row.error_message = error
            if output_path:
                row.output_path = output_path
            row.confidence_json = json.dumps(confidence) if confidence else None
            row.validation_json = json.dumps(validation) if validation else None
            row.extraction_validation_json = (
                json.dumps(extraction_validation) if extraction_validation else None
            )
            row.result_json = json.dumps(result) if result else None
            row.mapper_llm = mapper_llm
            row.validator_llm = validator_llm
            elapsed_ms = None
            elapsed = None
            if isinstance(result, dict):
                raw_ms = result.get("elapsed_ms")
                if isinstance(raw_ms, bool):
                    raw_ms = None
                if isinstance(raw_ms, (int, float)):
                    elapsed_ms = float(raw_ms)
                elif isinstance(raw_ms, str) and raw_ms.strip():
                    try:
                        elapsed_ms = float(raw_ms.strip())
                    except ValueError:
                        elapsed_ms = None
                raw_elapsed = result.get("elapsed")
                if isinstance(raw_elapsed, str) and raw_elapsed.strip():
                    elapsed = raw_elapsed.strip()
            row.elapsed_ms = elapsed_ms
            row.elapsed = elapsed
            if not getattr(row, "mcp", None):
                row.mcp = DOCUMENT_MCP
            if confidence or validation or extraction_validation:
                self._upsert_accuracy_report(
                    session,
                    job_id=job_id,
                    xid=row.xid,
                    confidence=confidence,
                    validation=validation,
                    extraction_validation=extraction_validation,
                    mapper_llm=mapper_llm,
                    validator_llm=validator_llm,
                    elapsed_ms=elapsed_ms,
                    elapsed=elapsed,
                    mcp=getattr(row, "mcp", None) or DOCUMENT_MCP,
                )

    def _upsert_accuracy_report(
        self,
        session: Session,
        *,
        job_id: str,
        xid: str | None,
        confidence: dict[str, Any] | None,
        validation: dict[str, Any] | None,
        extraction_validation: dict[str, Any] | None,
        mapper_llm: str | None,
        validator_llm: str | None,
        elapsed_ms: float | None = None,
        elapsed: str | None = None,
        mcp: str | None = None,
    ) -> None:
        now = _now_iso()
        scores = (confidence or {}).get("scores_pct") if isinstance(confidence, dict) else None
        if not isinstance(scores, dict):
            scores = {}

        def _pct(*keys: str) -> float | None:
            for key in keys:
                val = scores.get(key)
                if isinstance(val, (int, float)):
                    return float(val)
            return None

        def _from_unit(key: str) -> float | None:
            raw = (confidence or {}).get(key)
            if isinstance(raw, (int, float)):
                return round(float(raw) * 100.0, 1)
            return None

        def _flag(value: Any) -> str | None:
            if value is True:
                return "true"
            if value is False:
                return "false"
            return None

        row = session.get(DocumentAccuracyReport, job_id)
        payload = dict(
            xid=xid,
            overall_confidence_pct=_pct("overall_confidence_pct") or _from_unit("overall_confidence"),
            extraction_confidence_pct=_pct("extraction_confidence_pct")
            or _from_unit("extraction_confidence"),
            mapping_confidence_pct=_pct("placeholder_mapping_confidence_pct")
            or _from_unit("mapping_confidence"),
            coverage_pct=_pct("placeholder_coverage_pct") or _from_unit("coverage_score"),
            table_mapping_confidence_pct=_pct("table_mapping_confidence_pct")
            or _from_unit("table_mapping_confidence"),
            generation_integrity_pct=_pct("generation_integrity_pct")
            or _from_unit("generation_integrity"),
            generation_confidence_pct=_pct("generation_confidence_pct")
            or _from_unit("generation_confidence"),
            validation_score_pct=_pct("validation_score_pct") or _from_unit("validation_score"),
            extraction_passed=_flag((confidence or {}).get("extraction_passed")),
            validation_passed=_flag(
                (confidence or {}).get("validation_passed")
                if confidence and confidence.get("validation_passed") is not None
                else (validation or {}).get("passed")
            ),
            mapper_llm=mapper_llm or (confidence or {}).get("mapper_llm"),
            validator_llm=validator_llm or (confidence or {}).get("validator_llm"),
            notes=((confidence or {}).get("notes") or "")[:500] or None,
            confidence_json=None,
            validation_json=json.dumps(validation) if validation else None,
            extraction_validation_json=json.dumps(extraction_validation)
            if extraction_validation
            else None,
            scores_pct_json=json.dumps(
                {
                    key: value
                    for key, value in scores.items()
                    if isinstance(value, (int, float, str, bool)) or value is None
                }
            )
            if scores
            else None,
            elapsed_ms=elapsed_ms,
            elapsed=elapsed,
            mcp=mcp or DOCUMENT_MCP,
            updated_at=now,
        )
        if row is None:
            session.add(DocumentAccuracyReport(job_id=job_id, created_at=now, **payload))
        else:
            for key, value in payload.items():
                setattr(row, key, value)

    def get_accuracy_report(self, job_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            row = session.get(DocumentAccuracyReport, job_id)
            if row is None:
                return None
            return {
                "job_id": row.job_id,
                "xid": row.xid,
                "overall_confidence_pct": row.overall_confidence_pct,
                "extraction_confidence_pct": row.extraction_confidence_pct,
                "mapping_confidence_pct": row.mapping_confidence_pct,
                "coverage_pct": row.coverage_pct,
                "table_mapping_confidence_pct": row.table_mapping_confidence_pct,
                "generation_integrity_pct": row.generation_integrity_pct,
                "generation_confidence_pct": row.generation_confidence_pct,
                "validation_score_pct": row.validation_score_pct,
                "extraction_passed": row.extraction_passed,
                "validation_passed": row.validation_passed,
                "mapper_llm": row.mapper_llm,
                "validator_llm": row.validator_llm,
                "notes": row.notes,
                "scores_pct": json.loads(row.scores_pct_json) if row.scores_pct_json else None,
                "confidence": json.loads(row.confidence_json) if row.confidence_json else None,
                "validation": json.loads(row.validation_json) if row.validation_json else None,
                "extraction_validation": json.loads(row.extraction_validation_json)
                if row.extraction_validation_json
                else None,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "elapsed_ms": getattr(row, "elapsed_ms", None),
                "elapsed": getattr(row, "elapsed", None),
                "mcp": getattr(row, "mcp", None),
            }

    def get_job(self, job_id: str) -> JobRecord:
        with self._session() as session:
            row = session.get(DocumentJob, job_id)
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            return _job_to_record(row)

    def list_document_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._session() as session:
            rows = session.scalars(
                select(DocumentJob).order_by(DocumentJob.created_at.desc()).limit(limit)
            ).all()
            return [_job_to_record(row).to_dict() for row in rows]

    def insert_call_log(
        self,
        *,
        xid: str,
        kind: str,
        name: str,
        status: str,
        job_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_json: str | None = None,
        response_json: str | None = None,
        error_message: str | None = None,
        latency_ms: float | None = None,
        meta_json: str | None = None,
        log_id: str | None = None,
    ) -> str:
        lid = log_id or str(uuid.uuid4())
        now = _now_iso()
        with self._session() as session:
            session.add(
                CallLog(
                    id=lid,
                    xid=xid,
                    job_id=job_id,
                    kind=kind,
                    name=name[:512],
                    status=status,
                    provider=provider,
                    model=model,
                    request_json=request_json,
                    response_json=response_json,
                    error_message=error_message,
                    latency_ms=latency_ms,
                    meta_json=meta_json,
                    created_at=now,
                )
            )
        return lid

    def list_call_logs_by_xid(self, xid: str, *, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._session() as session:
            rows = session.scalars(
                select(CallLog)
                .where(CallLog.xid == xid)
                .order_by(CallLog.created_at.asc())
                .limit(limit)
            ).all()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = {
                "log_id": row.id,
                "xid": row.xid,
                "job_id": row.job_id,
                "kind": row.kind,
                "name": row.name,
                "status": row.status,
                "provider": row.provider,
                "model": row.model,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at,
            }
            for key, raw in (
                ("request", row.request_json),
                ("response", row.response_json),
                ("meta", row.meta_json),
            ):
                if raw:
                    try:
                        data[key] = json.loads(raw)
                    except json.JSONDecodeError:
                        data[key] = raw
                else:
                    data[key] = None
            out.append(data)
        return out

    def get_trace_by_xid(self, xid: str) -> dict[str, Any]:
        with self._session() as session:
            job_rows = session.scalars(
                select(DocumentJob)
                .where(DocumentJob.xid == xid)
                .order_by(DocumentJob.created_at.desc())
            ).all()
            jobs = [_job_to_record(row).to_dict() for row in job_rows]
        logs = self.list_call_logs_by_xid(xid)
        return {
            "xid": xid,
            "job_count": len(jobs),
            "log_count": len(logs),
            "jobs": jobs,
            "logs": logs,
        }

    def delete_job(self, job_id: str) -> None:
        with self._session() as session:
            row = session.get(DocumentJob, job_id)
            if row is not None:
                session.delete(row)
        blobs = get_blob_store()
        if blobs.enabled:
            blobs.delete_prefix(blob_job_root(job_id))
        job_dir = self.cfg.job_dir(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)

    def save_transcription(
        self,
        transcription_id: str,
        audio_path: Path,
        transcript: str,
        provider: str,
        model: str,
    ) -> None:
        now = _now_iso()
        with self._session() as session:
            session.add(
                TranscriptionJob(
                    id=transcription_id,
                    status="completed",
                    audio_path=str(audio_path),
                    transcript=transcript,
                    provider=provider,
                    model=model,
                    created_at=now,
                    completed_at=now,
                )
            )

    def get_transcription(self, transcription_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(TranscriptionJob, transcription_id)
            if row is None:
                raise KeyError(f"Transcription not found: {transcription_id}")
            return {
                "id": row.id,
                "status": row.status,
                "audio_path": row.audio_path,
                "transcript": row.transcript,
                "provider": row.provider,
                "model": row.model,
                "error_message": row.error_message,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }

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
        cid = contract_id or str(uuid.uuid4())
        now = _now_iso()
        entity = legal_entity or contact
        contact_name = None
        if entity:
            contact_name = (
                str(entity.get("legalName") or entity.get("name") or entity.get("code") or "")
                or None
            )
        with self._session() as session:
            session.add(
                VoiceContract(
                    id=cid,
                    status=status,
                    spoken_name=spoken_name,
                    spoken_number=spoken_number,
                    contact_name=contact_name,
                    contact_json=json.dumps(entity) if entity else None,
                    legal_entity_json=json.dumps(legal_entity) if legal_entity else None,
                    pricelist_json=json.dumps(pricelist) if pricelist else None,
                    contract_payload_json=json.dumps(contract_payload) if contract_payload else None,
                    contract_file=contract_file,
                    transcript=transcript,
                    transcription_id=transcription_id,
                    created_at=now,
                )
            )
        return self.get_voice_contract(cid)

    def get_voice_contract(self, contract_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(VoiceContract, contract_id)
            if row is None:
                raise KeyError(f"Voice contract not found: {contract_id}")
            return self._voice_to_dict(row)

    def list_voice_contracts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._session() as session:
            rows = session.scalars(
                select(VoiceContract).order_by(VoiceContract.created_at.desc()).limit(limit)
            ).all()
            return [self._voice_to_dict(row) for row in rows]

    @staticmethod
    def _voice_to_dict(row: VoiceContract) -> dict[str, Any]:
        data: dict[str, Any] = {
            "contract_id": row.id,
            "status": row.status,
            "spoken_name": row.spoken_name,
            "spoken_number": row.spoken_number,
            "contact_name": row.contact_name,
            "contract_file": row.contract_file,
            "transcript": row.transcript,
            "transcription_id": row.transcription_id,
            "created_at": row.created_at,
        }
        for src, dst in (
            (row.contact_json, "contact"),
            (row.legal_entity_json, "legal_entity"),
            (row.pricelist_json, "pricelist"),
            (row.contract_payload_json, "contract_payload"),
        ):
            data[dst] = json.loads(src) if src else None
        return data

    def _catalog_path(self) -> Path | None:
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "samples" / "data" / "contract_catalog.json"
            if candidate.is_file():
                return candidate
        return None

    def _load_contract_catalog(self) -> dict[str, Any]:
        """Voice HITL dummy catalog from JSON — not used for document template fill."""
        path = self._catalog_path()
        if path is None or not path.is_file():
            return {"legal_entities": [], "pricelists": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def find_legal_entity(self, name_or_code: str) -> dict[str, Any] | None:
        needle = " ".join((name_or_code or "").lower().split())
        if not needle:
            return None
        exact: dict[str, Any] | None = None
        partial: dict[str, Any] | None = None
        for entity in self._load_contract_catalog().get("legal_entities") or []:
            if not isinstance(entity, dict):
                continue
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
        needle = re.sub(r"[\s\-_]+", "", (contract_reference_number or "").upper())
        if not needle:
            return []
        scored: list[tuple[int, dict[str, Any]]] = []
        wanted_code = (legal_entity_code or "").strip().upper() or None
        for pricelist in self._load_contract_catalog().get("pricelists") or []:
            if not isinstance(pricelist, dict):
                continue
            ref = str(pricelist.get("contractReferenceNumber") or "")
            compact = re.sub(r"[\s\-_]+", "", ref.upper())
            code = str(pricelist.get("legalEntityCode") or "").upper()
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
                scored.append((score, pricelist))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]
