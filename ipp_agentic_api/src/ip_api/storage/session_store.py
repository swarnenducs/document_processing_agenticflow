"""SQLAlchemy persistence for client sessions (Azure SQL or SQLite)."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ip_api.core.settings import settings
from ip_api.storage.db import ensure_schema, get_session_factory
from ip_api.storage.models import SessionRequest, SessionRow


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_session_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: str | None
    user_email: str | None
    created_at: str
    updated_at: str
    last_request_kind: str | None = None
    last_xid: str | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_request_kind": self.last_request_kind,
            "last_xid": self.last_xid,
            "meta": self.meta or {},
        }


class SessionStore:
    """Sessions live in the same SQLAlchemy database as jobs."""

    def __init__(self, db_path: Path | None = None) -> None:
        cfg = settings()
        self.db_path = db_path or cfg.sqlite_database_path
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

    def get(self, session_id: str) -> SessionRecord | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        with self._session() as session:
            row = session.get(SessionRow, sid)
            if not row:
                return None
            return self._row_to_record(row)

    def ensure(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        user_email: str | None = None,
        request_kind: str | None = None,
        xid: str | None = None,
        path: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> SessionRecord:
        """Reuse existing session_id or create a new one; always touch updated_at."""
        now = _now_iso()
        uid = (user_id or "").strip() or None
        email = (user_email or "").strip() or None
        kind = (request_kind or "").strip() or None
        corr = (xid or "").strip() or None
        existing_id = (session_id or "").strip() or None

        with self._session() as session:
            row = session.get(SessionRow, existing_id) if existing_id else None

            if row is None:
                sid = existing_id or new_session_id()
                row = SessionRow(
                    session_id=sid,
                    user_id=uid,
                    user_email=email,
                    created_at=now,
                    updated_at=now,
                    last_request_kind=kind,
                    last_xid=corr,
                    meta_json=json.dumps(meta or {}),
                )
                session.add(row)
            else:
                sid = row.session_id
                row.user_id = uid or row.user_id
                row.user_email = email or row.user_email
                row.updated_at = now
                if kind:
                    row.last_request_kind = kind
                if corr:
                    row.last_xid = corr
                prev_meta: dict[str, Any] = {}
                if row.meta_json:
                    try:
                        prev_meta = json.loads(row.meta_json)
                    except json.JSONDecodeError:
                        prev_meta = {}
                if meta:
                    prev_meta = {**prev_meta, **meta}
                row.meta_json = json.dumps(prev_meta)

            session.add(
                SessionRequest(
                    id=uuid.uuid4().hex,
                    session_id=sid,
                    xid=corr,
                    request_kind=kind or "unknown",
                    path=path,
                    created_at=now,
                )
            )
            session.flush()
            return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: SessionRow) -> SessionRecord:
        parsed: dict[str, Any] | None = None
        raw = row.meta_json
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"raw": raw}
        return SessionRecord(
            session_id=str(row.session_id),
            user_id=row.user_id,
            user_email=row.user_email,
            created_at=str(row.created_at),
            updated_at=str(row.updated_at),
            last_request_kind=row.last_request_kind,
            last_xid=row.last_xid,
            meta=parsed,
        )


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store


def reset_session_store() -> None:
    global _store
    _store = None
