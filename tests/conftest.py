"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_llm_api_keys_in_tests(monkeypatch):
    """Tests use rule-based fallback unless explicitly mocking LLM calls."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
