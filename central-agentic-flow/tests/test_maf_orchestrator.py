"""Unit tests for MAF client resolution (no live LLM/MCP calls)."""

from __future__ import annotations

import pytest


def test_resolve_maf_chat_client_openai(monkeypatch):
    monkeypatch.delenv("MAF_MODEL_ID", raising=False)
    monkeypatch.setenv("MAF_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MAF_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("MAF_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    client = resolve_maf_chat_client()
    assert type(client).__name__ == "OpenAIChatClient"


def test_resolve_maf_chat_client_foundry_v1(monkeypatch):
    monkeypatch.delenv("MAF_MODEL_ID", raising=False)
    monkeypatch.setenv("MAF_PROVIDER", "azure_openai")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://demo.services.ai.azure.com/openai/v1/responses",
    )
    monkeypatch.setenv("MAF_MODEL", "gpt-5-mini")
    monkeypatch.delenv("MAF_LLM_BASE_URL", raising=False)

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    client = resolve_maf_chat_client()
    assert type(client).__name__ == "OpenAIChatClient"


def test_resolve_maf_chat_client_groq(monkeypatch):
    monkeypatch.delenv("MAF_MODEL_ID", raising=False)
    monkeypatch.setenv("MAF_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("MAF_MODEL", "llama-3.3-70b-versatile")

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    client = resolve_maf_chat_client()
    assert type(client).__name__ == "OpenAIChatClient"


def test_resolve_maf_chat_client_model_id_openai_foundry(monkeypatch):
    monkeypatch.setenv("MAF_MODEL_ID", "openai:gpt-5-mini")
    monkeypatch.delenv("MAF_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAF_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://demo.services.ai.azure.com/openai/v1/responses",
    )

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    client = resolve_maf_chat_client()
    assert type(client).__name__ == "OpenAIChatClient"


def test_resolve_maf_chat_client_missing_key(monkeypatch):
    monkeypatch.delenv("MAF_MODEL_ID", raising=False)
    monkeypatch.setenv("MAF_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAF_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("MAF_LLM_BASE_URL", raising=False)

    from central_agentic_flow.orchestrator import resolve_maf_chat_client

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        resolve_maf_chat_client()


def test_mcp_urls_defaults(monkeypatch):
    monkeypatch.delenv("DOCUMENT_MCP_URL", raising=False)
    monkeypatch.delenv("VOICE_MCP_URL", raising=False)

    from central_agentic_flow.mcp_registry import (
        document_mcp_url,
        voice_mcp_url,
    )

    assert document_mcp_url().endswith("/mcp")
    assert "8001" in document_mcp_url()
    assert "8002" in voice_mcp_url()


def test_yaml_registry_loads_document_and_voice(monkeypatch):
    monkeypatch.delenv("MAF_EXTRA_MCPS", raising=False)
    monkeypatch.delenv("MAF_MCP_SERVERS", raising=False)
    monkeypatch.delenv("MAF_MCP_REGISTRY_FILE", raising=False)

    from central_agentic_flow.mcp_registry import (
        ask_mcp_servers,
        build_agent_instructions,
        get_mcp_server,
        load_mcp_registry,
        reset_mcp_registry,
    )

    reset_mcp_registry()
    names = [s.name for s in load_mcp_registry()]
    assert names[:2] == ["contract-autocreation-mcp", "voice-agent"]
    assert "fabric-sql-agent" not in names
    document = next(s for s in load_mcp_registry() if s.name == "contract-autocreation-mcp")
    assert document.allows_ask()
    assert document.allows_jobs()
    assert document.default_tool == "generate_document"
    assert document.tool_rule("generate_document") is not None
    assert get_mcp_server("document").name == "contract-autocreation-mcp"
    assert get_mcp_server("template-auto-creation").name == "contract-autocreation-mcp"
    assert get_mcp_server("contract-autocreation-mcp").name == "contract-autocreation-mcp"
    assert get_mcp_server("contract_autocreation_mcp").name == "contract-autocreation-mcp"
    assert document.mcp_key == "contract_autocreation_mcp"
    assert get_mcp_server("voice").name == "voice-agent"
    assert get_mcp_server("voice-agent").name == "voice-agent"
    assert all(s.allows_ask() for s in ask_mcp_servers())
    prompt = build_agent_instructions(preamble="Preamble.")
    assert "document_generate_document" in prompt
    assert "voice_start_voice_contract" in prompt


def test_yaml_registry_extra_server_and_invoke_modes(tmp_path, monkeypatch):
    yaml_path = tmp_path / "mcp_registry.yml"
    yaml_path.write_text(
        """
servers:
  - name: jobs_only
    enabled: true
    url: http://127.0.0.1:9001/mcp
    prefix: jobs_only
    invoke:
      modes: [jobs]
      tools:
        do_job:
          when: "Deterministic job tool."
  - name: ask_only
    enabled: true
    url: http://127.0.0.1:9002/mcp
    prefix: ask_only
    invoke:
      modes: [ask]
      default_tool: chat
      tools:
        chat:
          when: "Natural-language only."
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAF_MCP_REGISTRY_FILE", str(yaml_path))
    monkeypatch.delenv("MAF_EXTRA_MCPS", raising=False)
    monkeypatch.delenv("MAF_MCP_SERVERS", raising=False)

    from central_agentic_flow.mcp_registry import (
        ask_mcp_servers,
        assert_jobs_invoke,
        get_mcp_server,
        load_mcp_registry,
        reset_mcp_registry,
    )

    reset_mcp_registry()
    names = [s.name for s in load_mcp_registry()]
    assert names == ["jobs_only", "ask_only"]
    assert [s.name for s in ask_mcp_servers()] == ["ask_only"]

    jobs = get_mcp_server("jobs_only")
    ask = get_mcp_server("ask_only")
    assert_jobs_invoke(jobs, "do_job")
    with pytest.raises(ValueError, match="not allowed for /invoke"):
        assert_jobs_invoke(ask, "chat")
    with pytest.raises(ValueError, match="not in invoke.tools"):
        assert_jobs_invoke(jobs, "secret_tool")


def test_extra_mcp_registry(monkeypatch):
    monkeypatch.setenv("MAF_EXTRA_MCPS", "invoice=http://127.0.0.1:8004/mcp")
    monkeypatch.setenv("MAF_MCP_INVOICE_DESCRIPTION", "Invoice matching")

    from central_agentic_flow.mcp_registry import (
        load_mcp_registry,
        reset_mcp_registry,
        resolve_server_and_tool,
    )

    reset_mcp_registry()
    names = [s.name for s in load_mcp_registry()]
    assert "contract-autocreation-mcp" in names
    assert "voice-agent" in names
    assert "invoice" in names
    spec, tool = resolve_server_and_tool(None, "invoice_match")
    assert spec.name == "invoice"
    assert tool == "match"


def test_expand_env_defaults(monkeypatch):
    monkeypatch.delenv("DOCUMENT_MCP_URL", raising=False)
    from central_agentic_flow.mcp_registry import expand_env

    assert expand_env("${DOCUMENT_MCP_URL:-http://127.0.0.1:8001/mcp}").endswith("/mcp")
    monkeypatch.setenv("DOCUMENT_MCP_URL", "http://example.local/mcp")
    assert expand_env("${DOCUMENT_MCP_URL:-http://127.0.0.1:8001/mcp}") == "http://example.local/mcp"
