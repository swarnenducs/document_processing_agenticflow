"""Unit tests for SQLite session create/reuse."""

from __future__ import annotations

from pathlib import Path

from ip_api.storage.session_store import SessionStore


def test_session_create_and_reuse(tmp_path: Path) -> None:
    db = tmp_path / "sessions.db"
    store = SessionStore(db_path=db)

    first = store.ensure(
        user_id="u1",
        user_email="u1@example.com",
        request_kind="maf",
        xid="xid-a",
        path="/api/ask",
    )
    assert first.session_id
    assert first.user_id == "u1"
    assert first.user_email == "u1@example.com"

    second = store.ensure(
        session_id=first.session_id,
        user_id="u1",
        request_kind="document",
        xid="xid-b",
        path="/api/v1/documents/jobs",
    )
    assert second.session_id == first.session_id
    assert second.last_request_kind == "document"
    assert second.last_xid == "xid-b"

    loaded = store.get(first.session_id)
    assert loaded is not None
    assert loaded.user_email == "u1@example.com"
