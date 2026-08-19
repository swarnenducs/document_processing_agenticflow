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
    server = VoiceProcessMCP(host="127.0.0.1", port=18002)
    payload = asyncio.run(call_tool(server, "health"))
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    from voice_enable_mcp.models.mcp_responses import McpHealthResponse

    McpHealthResponse.model_validate(payload)
    assert payload["mcp"] == "voice_process_mcp"
    assert payload["agent"] == "voice_process_mcp"
