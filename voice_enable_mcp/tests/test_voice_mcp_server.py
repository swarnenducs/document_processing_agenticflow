"""Tests for voice_process_mcp FastMCP tools."""

from __future__ import annotations

import asyncio

from voice_mcp_helpers import call_tool, list_tool_names
from voice_enable_mcp.server import VoiceProcessMCP


def test_voice_mcp_lists_tools() -> None:
    server = VoiceProcessMCP(host="127.0.0.1", port=18002)
    tools = asyncio.run(list_tool_names(server))
    assert "health" in tools
    assert "start_voice_contract" in tools
    assert "confirm_voice_contract" in tools


def test_voice_mcp_health() -> None:
    from voice_enable_mcp.core.dependencies import get_job_store
    from voice_enable_mcp.storage.job_store import JobStore

    server = VoiceProcessMCP(host="127.0.0.1", port=18002)
    payload = asyncio.run(call_tool(server, "health"))
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    from voice_enable_mcp.models.mcp_responses import McpHealthResponse

    McpHealthResponse.model_validate(payload)
    assert payload["mcp"] == "voice_process_mcp"
    assert payload["agent"] == "voice_process_mcp"
    assert isinstance(get_job_store(), JobStore)


def test_voice_mcp_hides_injected_store() -> None:
    """Bound methods + Depends must not expose self or store to the client."""
    from fastmcp import Client

    server = VoiceProcessMCP(host="127.0.0.1", port=18002)

    async def _schema() -> dict[str, object]:
        async with Client(server) as client:
            tools = await client.list_tools()
            start = next(t for t in tools if t.name == "start_voice_contract")
            listed = next(t for t in tools if t.name == "list_voice_contracts")
            return {
                "start": set((start.inputSchema or {}).get("properties") or {}),
                "list": set((listed.inputSchema or {}).get("properties") or {}),
            }

    schemas = asyncio.run(_schema())
    assert "self" not in schemas["start"]
    assert "store" not in schemas["start"]
    assert "transcript" in schemas["start"]
    assert "self" not in schemas["list"]
    assert "store" not in schemas["list"]
