"""FastAPI agent proxy routes + MCP result unwrap (this package only)."""

from __future__ import annotations

from ip_api.api.main import create_app
from ip_api.mcp_client import tool_result_payload


def test_tool_result_payload_prefers_data() -> None:
    class _R:
        data = {"ok": True}
        structured_content = None
        content = []
        is_error = False

    assert tool_result_payload(_R()) == {"ok": True}


def test_tool_result_payload_prefers_structured_content_dict() -> None:
    class _R:
        data = object()
        structured_content = {"ok": True, "mcp": "document_process_mcp"}
        content = []
        is_error = False

    assert tool_result_payload(_R()) == {"ok": True, "mcp": "document_process_mcp"}


def test_fastapi_exposes_agent_routes() -> None:
    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/agents/health" in paths
    assert "/api/v1/agents/document/generate" in paths
    assert "/api/v1/agents/voice/contract" in paths
