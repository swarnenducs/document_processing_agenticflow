"""Clear live provider keys so unit tests never call external LLMs."""

from __future__ import annotations

import pytest


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
