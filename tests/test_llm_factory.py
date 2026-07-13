"""Tests for dual-LLM configuration (mapper OpenAI, validator Groq)."""

from __future__ import annotations

from document_processing_agenticflow.services.llm_factory import (
    mapper_config,
    validator_config,
)


def test_mapper_config_defaults_to_openai_gpt5(monkeypatch) -> None:
    monkeypatch.setenv("MAPPER_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    cfg = mapper_config()
    assert cfg.role == "mapper"
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-5"
    assert cfg.label == "openai/gpt-5"


def test_validator_config_defaults_to_groq(monkeypatch) -> None:
    monkeypatch.setenv("VALIDATOR_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_VALIDATOR_MODEL", "openai/gpt-oss-120b")
    cfg = validator_config()
    assert cfg.role == "validator"
    assert cfg.provider == "groq"
    assert cfg.model == "openai/gpt-oss-120b"
    assert cfg.label == "groq/openai/gpt-oss-120b"


def test_validator_can_fallback_to_openai(monkeypatch) -> None:
    monkeypatch.setenv("VALIDATOR_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_VALIDATOR_MODEL", "gpt-5")
    cfg = validator_config()
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-5"


def test_is_mapper_available(monkeypatch) -> None:
    from document_processing_agenticflow.services.llm_factory import is_mapper_available

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_mapper_available() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert is_mapper_available() is True


def test_is_validator_available_groq(monkeypatch) -> None:
    from document_processing_agenticflow.services.llm_factory import is_validator_available

    monkeypatch.setenv("VALIDATOR_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert is_validator_available() is False
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert is_validator_available() is True
