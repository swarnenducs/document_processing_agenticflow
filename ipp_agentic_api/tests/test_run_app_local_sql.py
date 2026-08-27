"""Local launcher ignores leftover Azure SQL unless opted in."""

from __future__ import annotations

import os

from ip_api.run_app import apply_local_storage_for_launcher


def test_local_launcher_drops_azure_sql(monkeypatch) -> None:
    monkeypatch.setenv("IPP_FORCE_SQLITE", "")
    monkeypatch.setenv("AZURE_SQL_SERVER", "example.database.windows.net")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret")
    monkeypatch.setenv("AZURE_SQL_DATABASE", "ipp-app-db")
    monkeypatch.delenv("IPP_USE_AZURE_SQL", raising=False)
    monkeypatch.delenv("IPP_USE_AZURE_BLOB", raising=False)
    apply_local_storage_for_launcher(use_azure_sql=False, use_azure_blob=False)
    assert os.environ["IPP_FORCE_SQLITE"] == "1"
    assert os.environ["AZURE_SQL_SERVER"] == ""
    assert os.environ["AZURE_SQL_PASSWORD"] == ""
    assert not (os.getenv("AZURE_SQL_SERVER") or "").strip()
    assert not (os.getenv("AZURE_SQL_PASSWORD") or "").strip()
    assert os.environ["FILE_STORAGE_BACKEND"] == "local"
    assert os.getenv("AZURE_SQL_DATABASE") == "ipp-app-db"


def test_force_sqlite_settings_ignore_azure_sql(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IPP_FORCE_SQLITE", "1")
    monkeypatch.setenv("AZURE_SQL_SERVER", "ipp-sql-serv.database.windows.net")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret")
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "azure_blob")
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    from ip_api.core.settings import reload_settings
    from ip_api.storage.db import build_database_url

    cfg = reload_settings()
    assert cfg.uses_azure_sql is False
    assert cfg.file_storage_backend == "local"
    assert build_database_url().startswith("sqlite:///")


def test_local_launcher_keeps_azure_sql_when_flag(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SQL_SERVER", "example.database.windows.net")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret")
    apply_local_storage_for_launcher(use_azure_sql=True, use_azure_blob=False)
    assert os.environ["AZURE_SQL_SERVER"] == "example.database.windows.net"
    assert "IPP_FORCE_SQLITE" not in os.environ or os.environ.get("IPP_FORCE_SQLITE") != "1"
    assert os.environ["FILE_STORAGE_BACKEND"] == "local"
