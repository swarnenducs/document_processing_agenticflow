"""API tests: MCP tools go through a MAF stand-in (no other packages)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from maf_invoke_double import invoke_tool_double


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
def api_calls_maf_not_mcp(monkeypatch):
    monkeypatch.setattr("ip_api.services.maf_client.invoke_tool", invoke_tool_double)
