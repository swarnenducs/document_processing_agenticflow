"""Ensure a SQLite-backed session for API / MAF requests."""

from __future__ import annotations

from typing import Any

from ip_api.core.request_context import (
    get_session_id,
    get_user_email,
    get_user_id,
    get_xid,
    set_session_id,
    set_user_email,
    set_user_id,
)
from ip_api.storage.session_store import SessionRecord, get_session_store


def ensure_request_session(
    *,
    request_kind: str,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    path: str | None = None,
    meta: dict[str, Any] | None = None,
) -> SessionRecord:
    """
    Create or reuse a session, persist to SQLite, bind ContextVars.

    Precedence for ids: explicit args → context (headers) → mint new session.
    """
    sid = (session_id or "").strip() or get_session_id()
    uid = (user_id or "").strip() or get_user_id()
    email = (user_email or "").strip() or get_user_email()

    record = get_session_store().ensure(
        session_id=sid,
        user_id=uid,
        user_email=email,
        request_kind=request_kind,
        xid=get_xid(),
        path=path,
        meta=meta,
    )
    set_session_id(record.session_id)
    if record.user_id:
        set_user_id(record.user_id)
    if record.user_email:
        set_user_email(record.user_email)
    return record
