"""MAF trace rows persist through SQLAlchemy (SQLite locally, Azure SQL in cloud)."""

from __future__ import annotations

from pathlib import Path

from central_agentic_flow.core.settings import reload_settings
from central_agentic_flow.storage.call_log_store import CallLogStore
from central_agentic_flow.storage.db import build_database_url, engine_uses_mssql


def test_sqlite_is_the_default_backend() -> None:
    url = build_database_url()

    assert url.startswith("sqlite:///")
    assert engine_uses_mssql(url) is False


def test_azure_sql_parts_build_an_mssql_url(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SQL_SERVER", "example.database.windows.net")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret")
    reload_settings()

    assert engine_uses_mssql(build_database_url()) is True
    reload_settings()


def test_trace_rows_round_trip() -> None:
    store = CallLogStore()

    log_id = store.insert_call_log(
        xid="xid-maf",
        kind="llm",
        name="orchestrator",
        status="ok",
        response_json='{"text": "done"}',
        latency_ms=8.0,
    )

    rows = store.list_call_logs_by_xid("xid-maf")

    assert [row["log_id"] for row in rows] == [log_id]
    assert rows[0]["response"] == {"text": "done"}
    assert rows[0]["request"] is None


def test_trace_log_writes_through_the_store(monkeypatch) -> None:
    """services.trace_log must resolve a real store, not a missing module."""
    from central_agentic_flow.core.request_context import set_xid
    from central_agentic_flow.services.trace_log import log_event

    token = set_xid("xid-trace")
    try:
        log_id = log_event(kind="http", name="POST /ask", status="ok")
    finally:
        from central_agentic_flow.core.request_context import reset_xid

        reset_xid(token)

    assert log_id is not None
    rows = CallLogStore().list_call_logs_by_xid("xid-trace")
    assert [row["log_id"] for row in rows] == [log_id]


def test_sqlite_file_lands_where_configured(tmp_path: Path) -> None:
    CallLogStore().insert_call_log(xid="xid-file", kind="tool", name="probe", status="ok")

    assert (tmp_path / "app.db").is_file()
