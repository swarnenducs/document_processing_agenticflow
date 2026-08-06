"""FastMCP client used by FastAPI to invoke document / voice agents."""

from __future__ import annotations

import os
import time
from typing import Any

from fastmcp import Client

from document_processing_agenticflow.core.request_context import require_xid
from document_processing_agenticflow.services.trace_log import log_event


def tool_result_payload(result: Any) -> Any:
    """Normalize FastMCP CallToolResult into a JSON-serializable payload."""
    if result.data is not None:
        return result.data
    if result.structured_content is not None:
        return result.structured_content
    texts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    if len(texts) == 1:
        return texts[0]
    return {"content": texts, "is_error": bool(result.is_error)}


class MCPAgentClient:
    """Thin async client around a FastMCP HTTP (or in-process) endpoint."""

    def __init__(self, url_or_server: str | Any, *, timeout: float = 300.0) -> None:
        self.target = url_or_server
        self.timeout = timeout

    async def list_tools(self) -> list[str]:
        async with Client(self.target, timeout=self.timeout) as client:
            tools = await client.list_tools()
            return [t.name for t in tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        xid = require_xid()
        started = time.perf_counter()
        args = arguments or {}
        try:
            async with Client(self.target, timeout=self.timeout) as client:
                result = await client.call_tool(name, args)
                payload = tool_result_payload(result)
            log_event(
                kind="mcp_tool",
                name=name,
                request_payload=args,
                response_payload=payload,
                status="ok",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                xid=xid,
                meta={"target": str(self.target)},
            )
            if isinstance(payload, dict) and "xid" not in payload:
                payload = {**payload, "xid": xid}
            return payload
        except Exception as exc:
            log_event(
                kind="mcp_tool",
                name=name,
                request_payload=args,
                status="error",
                error=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                xid=xid,
                meta={"target": str(self.target)},
            )
            raise

    async def health(self) -> dict[str, Any]:
        try:
            payload = await self.call_tool("health")
            if isinstance(payload, dict):
                return payload
            return {"ok": True, "payload": payload}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


def get_document_mcp_client() -> MCPAgentClient:
    return MCPAgentClient(os.getenv("DOCUMENT_MCP_URL", "http://127.0.0.1:8001/mcp").rstrip("/"))


def get_voice_mcp_client() -> MCPAgentClient:
    return MCPAgentClient(os.getenv("VOICE_MCP_URL", "http://127.0.0.1:8002/mcp").rstrip("/"))
