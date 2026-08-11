"""Unit tests for MAF client resolution (no live LLM/MCP calls)."""

from __future__ import annotations

import pytest


def test_resolve_maf_chat_client_openai(monkeypatch):
    monkeypatch.setenv("MAF_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MAF_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("MAF_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    client = resolve_maf_chat_client()
    assert type(client).__name__ == "OpenAIChatClient"


def test_resolve_maf_chat_client_groq(monkeypatch):
    monkeypatch.setenv("MAF_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("MAF_MODEL", "llama-3.3-70b-versatile")

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    client = resolve_maf_chat_client()
    assert type(client).__name__ == "OpenAIChatClient"


def test_resolve_maf_chat_client_missing_key(monkeypatch):
    monkeypatch.setenv("MAF_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAF_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        resolve_maf_chat_client()


def test_mcp_urls_defaults(monkeypatch):
    monkeypatch.delenv("DOCUMENT_MCP_URL", raising=False)
    monkeypatch.delenv("VOICE_MCP_URL", raising=False)

    from central_agentic_flow.orchestrator import (
        document_mcp_url,
        voice_mcp_url,
    )

    assert document_mcp_url().endswith("/mcp")
    assert "8001" in document_mcp_url()
    assert "8002" in voice_mcp_url()
