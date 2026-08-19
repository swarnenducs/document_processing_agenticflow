"""FastMCP client used by FastAPI to invoke document / voice agents."""

from __future__ import annotations

import os
import time
from typing import Any

from fastmcp import Client

from ip_api.core.request_context import require_xid
from ip_api.services.trace_log import log_event


def _jsonable(value: Any) -> Any:
    """Pydantic / FastMCP Root → JSON-serializable dict."""
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    json_fn = getattr(value, "model_dump_json", None)
    if callable(json_fn):
        import json

        return json.loads(json_fn())
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            dumped = dump(mode="json")
        except TypeError:
            dumped = dump()
        if isinstance(dumped, dict):
            return dumped
        if dumped is not value:
            return _jsonable(dumped)
    fields = getattr(type(value), "model_fields", None)
    if fields:
        return {name: _jsonable(getattr(value, name, None)) for name in fields}
    try:
        dumped = vars(value)
        if isinstance(dumped, dict) and dumped:
            return dumped
    except TypeError:
        pass
    return value


def tool_result_payload(result: Any) -> Any:
    """Normalize FastMCP CallToolResult into a JSON object (dict)."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    data = getattr(result, "data", None)
    converted = _jsonable(data)
    if isinstance(converted, dict):
        return converted
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
        from ip_api.flow_debug import flow_breakpoint

        xid = require_xid()
        started = time.perf_counter()
        args = arguments or {}
        flow_breakpoint("mcp_call_tool", tool_name=name, xid=xid)
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
