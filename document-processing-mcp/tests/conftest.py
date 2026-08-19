"""Clear live provider keys so unit tests never call external LLMs."""

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
