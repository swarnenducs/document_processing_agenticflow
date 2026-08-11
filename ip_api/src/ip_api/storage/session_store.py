"""SQLite persistence for client sessions (Phase 1: id + user identity)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from ip_api.core.settings import settings


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
    """Sessions live in the same SQLite DB as jobs (configurable path)."""

    def __init__(self, db_path: Path | None = None) -> None:
        cfg = settings()
        self.db_path = db_path or cfg.sqlite_database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    user_email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_request_kind TEXT,
                    last_xid TEXT,
                    meta_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_requests (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    xid TEXT,
                    request_kind TEXT NOT NULL,
                    path TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_requests_session "
                "ON session_requests(session_id)"
            )

    def get(self, session_id: str) -> SessionRecord | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (sid,),
            ).fetchone()
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

        with self._conn() as conn:
            row = None
            if existing_id:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (existing_id,),
                ).fetchone()

            if row is None:
                sid = existing_id or new_session_id()
                conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, user_id, user_email, created_at, updated_at,
                        last_request_kind, last_xid, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        uid,
                        email,
                        now,
                        now,
                        kind,
                        corr,
                        json.dumps(meta or {}),
                    ),
                )
            else:
                sid = str(row["session_id"])
                # Prefer newly provided identity; keep prior if blank
                next_uid = uid or row["user_id"]
                next_email = email or row["user_email"]
                prev_meta: dict[str, Any] = {}
                if row["meta_json"]:
                    try:
                        prev_meta = json.loads(row["meta_json"])
                    except json.JSONDecodeError:
                        prev_meta = {}
                if meta:
                    prev_meta = {**prev_meta, **meta}
                conn.execute(
                    """
                    UPDATE sessions
                    SET user_id = ?, user_email = ?, updated_at = ?,
                        last_request_kind = COALESCE(?, last_request_kind),
                        last_xid = COALESCE(?, last_xid),
                        meta_json = ?
                    WHERE session_id = ?
                    """,
                    (
                        next_uid,
                        next_email,
                        now,
                        kind,
                        corr,
                        json.dumps(prev_meta),
                        sid,
                    ),
                )

            conn.execute(
                """
                INSERT INTO session_requests (
                    id, session_id, xid, request_kind, path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    sid,
                    corr,
                    kind or "unknown",
                    path,
                    now,
                ),
            )

            out = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (sid,),
            ).fetchone()

        assert out is not None
        return self._row_to_record(out)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SessionRecord:
        meta: dict[str, Any] | None = None
        raw = row["meta_json"]
        if raw:
            try:
                meta = json.loads(raw)
            except json.JSONDecodeError:
                meta = {"raw": raw}
        return SessionRecord(
            session_id=str(row["session_id"]),
            user_id=row["user_id"],
            user_email=row["user_email"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_request_kind=row["last_request_kind"],
            last_xid=row["last_xid"],
            meta=meta,
        )


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
