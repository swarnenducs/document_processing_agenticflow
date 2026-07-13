"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_llm_api_keys_in_tests(monkeypatch):
    """Clear live provider keys so unit tests never call external LLMs."""
    for key in (
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "MAPPER_API_KEY",
        "VALIDATOR_API_KEY",
        "SPEECH_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
