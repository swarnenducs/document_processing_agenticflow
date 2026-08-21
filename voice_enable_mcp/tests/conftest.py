"""Keep unit tests off external LLMs and off Azure SQL."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))


@pytest.fixture(autouse=True)
def no_llm_api_keys_in_tests(monkeypatch):
    for key in (
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "MAPPER_API_KEY",
        "VALIDATOR_API_KEY",
        "SPEECH_API_KEY",
        "MAPPER_MODEL_ID",
        "VALIDATOR_MODEL_ID",
        "AGENT_MODEL_ID",
        "MAF_MODEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def local_sqlite_only(tmp_path, monkeypatch):
    """Pin storage and the SQLAlchemy engine to tmp_path SQLite, never Azure SQL."""
    from voice_enable_mcp.core.settings import reload_settings

    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    for key in ("AZURE_SQL_SERVER", "AZURE_SQL_PASSWORD", "SQLALCHEMY_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    reload_settings()
    yield
    reload_settings()
