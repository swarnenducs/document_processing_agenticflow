"""Tests for separate document_process_mcp / voice_process_mcp FastMCP servers."""

from __future__ import annotations

import asyncio

from document_processing_agenticflow.mcp.client import MCPAgentClient, tool_result_payload
from document_processing_agenticflow.mcp.document_process_mcp import DocumentProcessMCP
from document_processing_agenticflow.mcp.voice_process_mcp import VoiceProcessMCP


def test_document_mcp_lists_tools() -> None:
    server = DocumentProcessMCP(host="127.0.0.1", port=18001)

    async def _run() -> list[str]:
        client = MCPAgentClient(server)
        return await client.list_tools()

    tools = asyncio.run(_run())
    assert "health" in tools
    assert "generate_document" in tools


def test_document_mcp_health() -> None:
    server = DocumentProcessMCP(host="127.0.0.1", port=18001)

    async def _run() -> dict:
        return await MCPAgentClient(server).call_tool("health")

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["mcp"] == "document_process_mcp"
    assert payload["agent"] == "document_process_mcp"


def test_voice_mcp_lists_tools() -> None:
    server = VoiceProcessMCP(host="127.0.0.1", port=18002)

    async def _run() -> list[str]:
        return await MCPAgentClient(server).list_tools()

    tools = asyncio.run(_run())
    assert "health" in tools
    assert "start_voice_contract" in tools
    assert "confirm_voice_contract" in tools


def test_voice_mcp_health() -> None:
    server = VoiceProcessMCP(host="127.0.0.1", port=18002)

    async def _run() -> dict:
        return await MCPAgentClient(server).call_tool("health")

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["mcp"] == "voice_process_mcp"
    assert payload["agent"] == "voice_process_mcp"


def test_tool_result_payload_prefers_data() -> None:
    class _R:
        data = {"ok": True}
        structured_content = None
        content = []
        is_error = False

    assert tool_result_payload(_R()) == {"ok": True}


def test_fastapi_exposes_agent_routes() -> None:
    from document_processing_agenticflow.api.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/agents/health" in paths
    assert "/api/v1/agents/document/generate" in paths
    assert "/api/v1/agents/voice/contract" in paths
