"""Dynaconf fills missing env from .env; Pydantic Settings reads process env."""

from __future__ import annotations

import os
from pathlib import Path

from central_agentic_flow.core.dynaconf_loader import _export_scalar, apply_dynaconf_from_env_files
from central_agentic_flow.core.settings import reload_settings


def test_export_scalar_does_not_override_process_env(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SQL_SERVER", "from-process")
    _export_scalar("AZURE_SQL_SERVER", "from-dotenv", override=False)
    assert os.environ["AZURE_SQL_SERVER"] == "from-process"


def test_pydantic_settings_reads_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("IPP_FORCE_SQLITE", "1")
    monkeypatch.setenv("AZURE_SQL_SERVER", "ipp-sql-serv.database.windows.net")
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "secret")
    cfg = reload_settings()
    assert cfg.uses_azure_sql is False
    assert cfg.storage_base_path == (tmp_path / "storage").resolve()


def test_apply_dynaconf_returns_loader() -> None:
    box = apply_dynaconf_from_env_files()
    assert box is not None
