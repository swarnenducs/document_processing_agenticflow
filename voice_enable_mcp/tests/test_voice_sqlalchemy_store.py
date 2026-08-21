"""Voice store goes through SQLAlchemy for both SQLite and Azure SQL."""

from __future__ import annotations

from pathlib import Path

from voice_enable_mcp.core.settings import reload_settings
from voice_enable_mcp.storage.db import build_database_url, engine_uses_mssql
from voice_enable_mcp.storage.job_store import JobStore


def test_sqlite_is_the_default_backend(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    reload_settings()

    url = build_database_url()

    assert url.startswith("sqlite:///")
    assert engine_uses_mssql(url) is False


def test_azure_sql_parts_build_an_mssql_url(tmp_path: Path, monkeypatch) -> None:
    """Set the same env as ip_api and the voice MCP follows to Azure SQL."""
    monkeypatch.setenv("AZURE_SQL_SERVER", "tcp:example.database.windows.net,1433")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret}value")
    monkeypatch.setenv("AZURE_SQL_DATABASE", "app-db")
    reload_settings()

    url = build_database_url()

    assert engine_uses_mssql(url) is True
    assert url.startswith("mssql+pyodbc:///?odbc_connect=")
    reload_settings()


def test_explicit_sqlalchemy_url_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URL", "sqlite:///" + str(tmp_path / "explicit.db"))
    monkeypatch.setenv("AZURE_SQL_SERVER", "example.database.windows.net")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret")
    reload_settings()

    assert build_database_url().endswith("explicit.db")
    reload_settings()


def test_voice_contract_round_trip() -> None:
    store = JobStore()

    saved = store.save_voice_contract(
        spoken_name="AVC",
        spoken_number="CR-1001",
        legal_entity={"code": "AVC", "legalName": "AVC Industries"},
        pricelist={"contractReferenceNumber": "CR-1001"},
        contract_payload={"total": 42},
        contract_file="/tmp/draft.docx",
        transcript="create contract",
    )

    assert saved["contract_id"]
    assert saved["contact_name"] == "AVC Industries"
    assert saved["legal_entity"]["code"] == "AVC"
    assert saved["contract_payload"]["total"] == 42

    fetched = store.get_voice_contract(saved["contract_id"])
    assert fetched["contract_file"] == "/tmp/draft.docx"

    listed = store.list_voice_contracts(limit=10)
    assert [row["contract_id"] for row in listed] == [saved["contract_id"]]


def test_call_log_round_trip_parses_json_columns() -> None:
    store = JobStore()

    log_id = store.insert_call_log(
        xid="xid-1",
        kind="tool",
        name="start_voice_contract",
        status="ok",
        request_json='{"transcript": "hi"}',
        meta_json='{"source": "test"}',
        latency_ms=12.5,
    )

    rows = store.list_call_logs_by_xid("xid-1")

    assert [row["log_id"] for row in rows] == [log_id]
    assert rows[0]["request"] == {"transcript": "hi"}
    assert rows[0]["meta"] == {"source": "test"}
    assert rows[0]["response"] is None
    assert rows[0]["latency_ms"] == 12.5


def test_contract_catalog_needs_no_seeding() -> None:
    """Catalog is JSON reference data, so lookups work on a fresh database."""
    store = JobStore()

    entity = store.find_legal_entity("AVC")

    assert entity is not None
    assert entity["code"] == "AVC"
    assert store.search_pricelists("CR 1001")
