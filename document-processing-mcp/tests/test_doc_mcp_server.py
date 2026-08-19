"""Tests for document_process_mcp FastMCP tools."""

from __future__ import annotations

import asyncio

from document_processing_mcp.server import DocumentProcessMCP
from doc_mcp_helpers import call_tool, list_tool_names


def test_document_mcp_lists_tools() -> None:
    server = DocumentProcessMCP(host="127.0.0.1", port=18001)
    tools = asyncio.run(list_tool_names(server))
    assert "health" in tools
    assert "generate_document" in tools


def test_document_mcp_health() -> None:
    server = DocumentProcessMCP(host="127.0.0.1", port=18001)
    payload = asyncio.run(call_tool(server, "health"))
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    from document_processing_mcp.models.mcp_responses import McpHealthResponse

    McpHealthResponse.model_validate(payload)
    assert payload["mcp"] == "document_process_mcp"
    assert payload["agent"] == "document_process_mcp"
    assert "blob_enabled" in payload
