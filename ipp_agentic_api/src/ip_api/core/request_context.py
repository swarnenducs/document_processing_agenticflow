"""Request correlation id (xid) + session / user identity via ContextVar."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

_xid: ContextVar[str | None] = ContextVar("xid", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_user_email: ContextVar[str | None] = ContextVar("user_email", default=None)

XID_HEADER = "X-Request-ID"
XID_HEADER_ALT = "X-Correlation-ID"
SESSION_HEADER = "X-Session-Id"
USER_ID_HEADER = "X-User-Id"
USER_EMAIL_HEADER = "X-User-Email"


def new_xid() -> str:
    """Mint a new correlation id (UUID4 hex, compact)."""
    return uuid.uuid4().hex


def get_xid() -> str | None:
    return _xid.get()


def require_xid() -> str:
    """Return current xid or mint one (CLI / background / MCP)."""
    current = _xid.get()
    if current:
        return current
    minted = new_xid()
    _xid.set(minted)
    return minted


def set_xid(xid: str | None) -> Token:
    return _xid.set(xid)


def reset_xid(token: Token) -> None:
    _xid.reset(token)


def get_job_id() -> str | None:
    return _job_id.get()


def set_job_id(job_id: str | None) -> Token:
    return _job_id.set(job_id)


def reset_job_id(token: Token) -> None:
    _job_id.reset(token)


def get_session_id() -> str | None:
    return _session_id.get()


def set_session_id(session_id: str | None) -> Token:
    return _session_id.set(session_id)


def reset_session_id(token: Token) -> None:
    _session_id.reset(token)


def get_user_id() -> str | None:
    return _user_id.get()


def set_user_id(user_id: str | None) -> Token:
    return _user_id.set(user_id)


def reset_user_id(token: Token) -> None:
    _user_id.reset(token)


def get_user_email() -> str | None:
    return _user_email.get()


def set_user_email(user_email: str | None) -> Token:
    return _user_email.set(user_email)


def reset_user_email(token: Token) -> None:
    _user_email.reset(token)


@contextmanager
def bind_xid(xid: str | None = None, *, job_id: str | None = None) -> Iterator[str]:
    """Bind xid (and optional job_id) for the duration of a block."""
    value = (xid or "").strip() or new_xid()
    xid_token = set_xid(value)
    job_token = set_job_id(job_id) if job_id is not None else None
    try:
        yield value
    finally:
        if job_token is not None:
            reset_job_id(job_token)
        reset_xid(xid_token)
