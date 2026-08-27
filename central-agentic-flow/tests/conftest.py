"""Keep unit tests off external LLMs and off Azure SQL."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def local_sqlite_only(tmp_path, monkeypatch):
    """Pin storage and the SQLAlchemy engine to tmp_path SQLite, never Azure SQL."""
    from central_agentic_flow.core.settings import reload_settings

    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    for key in ("AZURE_SQL_SERVER", "AZURE_SQL_PASSWORD", "SQLALCHEMY_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    reload_settings()
    yield
    reload_settings()


@pytest.fixture(autouse=True)
def component_prompts_dir(monkeypatch):
    from pathlib import Path

    monkeypatch.setenv(
        "MAF_PROMPTS_DIR",
        str(Path(__file__).resolve().parents[1] / "prompts"),
    )
    monkeypatch.setenv(
        "MAF_PROMPT_VERSIONS_FILE",
        str(Path(__file__).resolve().parents[1] / "config" / "prompt_versions.json"),
    )


@pytest.fixture(autouse=True)
def no_llm_api_keys_in_tests(monkeypatch):
    for key in (
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "MAF_API_KEY",
        "MAF_MODEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)
