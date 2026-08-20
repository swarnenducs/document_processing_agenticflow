"""Foundry hosted-agent adapter tests (no Azure calls)."""

from __future__ import annotations

from central_agentic_flow.foundry_server import (
    build_foundry_instructions,
    missing_foundry_settings,
    toolbox_configured,
)


def test_missing_foundry_settings(monkeypatch) -> None:
    for name in ("FOUNDRY_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME"):
        monkeypatch.delenv(name, raising=False)

    assert missing_foundry_settings() == [
        "FOUNDRY_PROJECT_ENDPOINT",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    ]


def test_foundry_settings_accept_configured_values(monkeypatch) -> None:
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/demo",
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")

    assert missing_foundry_settings() == []


def test_toolbox_is_optional(monkeypatch) -> None:
    """No business MCP configured yet, so the toolbox must stay optional."""
    monkeypatch.delenv("TOOLBOX_ENDPOINT", raising=False)
    assert toolbox_configured() is False

    monkeypatch.setenv("TOOLBOX_ENDPOINT", "...")
    assert toolbox_configured() is False

    monkeypatch.setenv(
        "TOOLBOX_ENDPOINT",
        "https://example.services.ai.azure.com/toolboxes/demo/mcp?api-version=v1",
    )
    assert toolbox_configured() is True


def test_foundry_instructions_are_business_only(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_MAF_INSTRUCTIONS", "Base orchestrator instructions.")

    instructions = build_foundry_instructions()

    assert "Base orchestrator instructions." in instructions
    assert "business___<tool_name>" in instructions
    assert "never call localhost" in instructions
    # Document and voice stay on the job path, so chat must not advertise them.
    assert "document___generate_document" not in instructions
    assert "voice___start_voice_contract" not in instructions
