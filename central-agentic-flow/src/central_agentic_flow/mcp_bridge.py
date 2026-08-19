"""Deterministic MCP calls owned by MAF (API never talks to MCP URLs)."""

from __future__ import annotations

from typing import Any

from central_agentic_flow.mcp_registry import (
    McpServerSpec,
    assert_jobs_invoke,
    load_mcp_registry,
    resolve_server_and_tool,
    spec_catalog_fields,
)
from central_agentic_flow.orchestrator import maf_request_timeout


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


def _tool_result_payload(result: Any) -> Any:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    converted = _jsonable(getattr(result, "data", None))
    if isinstance(converted, dict):
        return converted
    texts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    if len(texts) == 1:
        return texts[0]
    return {"content": texts, "is_error": bool(getattr(result, "is_error", False))}


async def invoke_mcp_tool(
    *,
    server: str | None,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from fastmcp import Client

    spec, tool_name = resolve_server_and_tool(server, tool)
    assert_jobs_invoke(spec, tool_name)
    timeout = float(maf_request_timeout())
    async with Client(spec.url, timeout=timeout) as client:
        result = await client.call_tool(tool_name, arguments or {})
        payload = _tool_result_payload(result)
    if not isinstance(payload, dict):
        payload = {"ok": True, "result": payload}
    return {
        "ok": bool(payload.get("ok", True)),
        "server": spec.name,
        "mcp": spec.mcp_key,
        "tool": tool_name,
        "result": payload,
    }


async def list_mcp_tools(spec: McpServerSpec) -> list[str]:
    from fastmcp import Client

    timeout = float(maf_request_timeout())
    async with Client(spec.url, timeout=timeout) as client:
        tools = await client.list_tools()
        return [t.name for t in tools]


async def ping_mcp(spec: McpServerSpec) -> dict[str, Any]:
    try:
        tools = await list_mcp_tools(spec)
        return {"ok": True, "tools": tools, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "tools": [], "error": str(exc)}


async def catalog_mcp_servers() -> dict[str, Any]:
    servers: list[dict[str, Any]] = []
    blocks: dict[str, Any] = {}
    for spec in load_mcp_registry():
        ping = await ping_mcp(spec)
        tools = ping.get("tools") or []
        row = {
            "name": spec.name,
            "mcp": spec.mcp_key,
            "url": spec.url,
            "prefix": spec.prefix,
            "description": spec.description,
            "available": bool(ping.get("ok")),
            "tools": tools,
            "maf_prefixed": [f"{spec.prefix}_{t}" for t in tools],
            "error": ping.get("error"),
            **spec_catalog_fields(spec),
        }
        servers.append(row)
        blocks[spec.mcp_key] = {
            "available": row["available"],
            "tools": tools,
            "maf_prefixed": row["maf_prefixed"],
            "error": row["error"],
        }
    return {
        "ok": all(row["available"] for row in servers) if servers else False,
        "orchestrator": "maf",
        "servers": servers,
        **blocks,
    }
