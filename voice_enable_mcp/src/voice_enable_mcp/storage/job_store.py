"""Voice contract + trace persistence through SQLAlchemy.

Rows go to whatever backend ``storage/db.py`` resolves (local SQLite or Azure
SQL). Generated contract files stay on the filesystem under STORAGE_BASE_PATH.

The legal entity / pricelist catalog is dummy HITL reference data read from
``samples/data/contract_catalog.json``, matching ip_api — it is deliberately not
a SQL table, so nothing has to be seeded before the voice flow can run.
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from voice_enable_mcp.core.settings import settings
from voice_enable_mcp.storage.db import ensure_schema, get_session_factory
from voice_enable_mcp.storage.models import CallLog, VoiceContract

_JSON_COLUMNS = ("request_json", "response_json", "meta_json")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    """Persist voice contracts and call logs; blobs live on disk."""

    def __init__(self, db_path: Path | None = None) -> None:
        cfg = settings()
        self.cfg = cfg
        self.db_path = db_path or cfg.sqlite_database_path
        # An explicit path pins SQLite; otherwise the configured backend wins.
        self._sqlite_override = db_path
        self._catalog: dict[str, Any] | None = None
        ensure_schema(sqlite_path=self._sqlite_override)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        factory = get_session_factory(sqlite_path=self._sqlite_override)
        session = factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Voice contracts
    # ------------------------------------------------------------------

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
                    contract_payload_json=(
                        json.dumps(contract_payload) if contract_payload else None
                    ),
                    contract_file=contract_file,
                    transcript=transcript,
                    transcription_id=transcription_id,
                    created_at=_now_iso(),
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
        capped = max(1, min(int(limit), 200))
        with self._session() as session:
            rows = session.scalars(
                select(VoiceContract).order_by(VoiceContract.created_at.desc()).limit(capped)
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

    # ------------------------------------------------------------------
    # Call logs (xid trace)
    # ------------------------------------------------------------------

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
        with self._session() as session:
            session.add(
                CallLog(
                    id=lid,
                    xid=xid,
                    job_id=job_id,
                    kind=kind,
                    name=name,
                    status=status,
                    provider=provider,
                    model=model,
                    request_json=request_json,
                    response_json=response_json,
                    error_message=error_message,
                    latency_ms=latency_ms,
                    meta_json=meta_json,
                    created_at=_now_iso(),
                )
            )
        return lid

    def list_call_logs_by_xid(self, xid: str, *, limit: int = 200) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), 500))
        with self._session() as session:
            rows = session.scalars(
                select(CallLog)
                .where(CallLog.xid == xid)
                .order_by(CallLog.created_at.asc())
                .limit(capped)
            ).all()
            return [self._call_log_to_dict(row) for row in rows]

    @staticmethod
    def _call_log_to_dict(row: CallLog) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        for column in _JSON_COLUMNS:
            raw = getattr(row, column)
            data[column] = raw
            key = column.removesuffix("_json")
            if not raw:
                data[key] = None
                continue
            try:
                data[key] = json.loads(raw)
            except json.JSONDecodeError:
                data[key] = raw
        return data

    # ------------------------------------------------------------------
    # Contract catalog (JSON reference data, not SQL)
    # ------------------------------------------------------------------

    def _catalog_path(self) -> Path | None:
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "samples" / "data" / "contract_catalog.json"
            if candidate.is_file():
                return candidate
        return None

    def _load_contract_catalog(self) -> dict[str, Any]:
        if self._catalog is not None:
            return self._catalog
        path = self._catalog_path()
        if path is None:
            self._catalog = {"legal_entities": [], "pricelists": []}
        else:
            self._catalog = json.loads(path.read_text(encoding="utf-8"))
        return self._catalog

    def ensure_contract_catalog_seeded(self) -> None:
        """Warm the JSON catalog cache. Kept so callers need no backend knowledge."""
        self._load_contract_catalog()

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
        """Fuzzy match contract refs ('CR 1001' ≈ 'CR-1001')."""
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
