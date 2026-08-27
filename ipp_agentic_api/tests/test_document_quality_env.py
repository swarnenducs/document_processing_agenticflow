"""Document retry / accuracy bar from environment variables."""

from __future__ import annotations

from ip_api.core.settings import get_settings, reload_settings


def test_document_quality_defaults(monkeypatch) -> None:
    for key in (
        "DOCUMENT_MAX_RETRIES",
        "MAX_RETRIES",
        "DOCUMENT_VALIDATION_THRESHOLD",
        "DOCUMENT_ACCURACY_THRESHOLD",
        "VALIDATION_THRESHOLD",
        "DOCUMENT_LLM_OPTIMIZATION_ENABLED",
        "DOCUMENT_LLM_ROUTING_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    reload_settings()
    cfg = get_settings()
    assert cfg.document_max_retries == 1
    assert cfg.document_validation_threshold == 0.7
    assert cfg.document_llm_optimization_enabled is False


def test_document_quality_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_MAX_RETRIES", "2")
    monkeypatch.setenv("DOCUMENT_VALIDATION_THRESHOLD", "0.85")
    reload_settings()
    cfg = get_settings()
    assert cfg.document_max_retries == 2
    assert cfg.document_validation_threshold == 0.85


def test_document_quality_clamps_and_aliases(monkeypatch) -> None:
    monkeypatch.setenv("MAX_RETRIES", "99")
    monkeypatch.setenv("DOCUMENT_ACCURACY_THRESHOLD", "1.4")
    monkeypatch.delenv("DOCUMENT_MAX_RETRIES", raising=False)
    monkeypatch.delenv("DOCUMENT_VALIDATION_THRESHOLD", raising=False)
    monkeypatch.delenv("VALIDATION_THRESHOLD", raising=False)
    reload_settings()
    cfg = get_settings()
    assert cfg.document_max_retries == 3
    assert cfg.document_validation_threshold == 1.0


def test_document_optimization_enabled_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_LLM_OPTIMIZATION_ENABLED", "true")
    reload_settings()
    assert get_settings().document_llm_optimization_enabled is True
