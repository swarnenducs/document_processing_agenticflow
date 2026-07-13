"""Tests for speech provider resolution and key fallbacks."""

from __future__ import annotations

import pytest

from document_processing_agenticflow.services.speech_to_text import resolve_speech_provider


def _clear_speech_env(monkeypatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "SPEECH_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "SPEECH_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_auto_prefers_azure_when_configured(monkeypatch) -> None:
    _clear_speech_env(monkeypatch)
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_speech_provider() == "azure_openai"


def test_auto_prefers_openai_when_keyed(monkeypatch) -> None:
    _clear_speech_env(monkeypatch)
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_speech_provider() == "openai"


def test_auto_falls_back_to_groq(monkeypatch) -> None:
    _clear_speech_env(monkeypatch)
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    assert resolve_speech_provider() == "groq"


def test_explicit_azure_alias(monkeypatch) -> None:
    _clear_speech_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    assert resolve_speech_provider("azure") == "azure_openai"


def test_openai_falls_back_to_groq_without_openai_key(monkeypatch) -> None:
    _clear_speech_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    assert resolve_speech_provider("openai") == "groq"


def test_missing_keys_raise_helpful_error(monkeypatch) -> None:
    _clear_speech_env(monkeypatch)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY missing|No speech credentials"):
        resolve_speech_provider("auto")
