"""ip_api talks only to the central agent (MAF) over HTTP. MAF is the only MCP caller."""

from __future__ import annotations

import os
from typing import Any

import httpx


def maf_base_url() -> str:
    return (os.getenv("MAF_BASE_URL") or os.getenv("MAF_URL") or "http://127.0.0.1:8003").rstrip(
        "/"
    )


def _timeout() -> float:
    try:
        return max(30.0, float(os.getenv("MAF_PROXY_TIMEOUT", "320")))
    except ValueError:
        return 320.0


async def invoke_tool(
    server: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Call an MCP tool through MAF. Returns the tool payload (unwrapped ``result``)."""
    url = f"{maf_base_url()}/invoke"
    payload = {"server": server, "tool": tool, "arguments": arguments or {}}
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code >= 400:
        detail: Any
        try:
            detail = resp.json()
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise RuntimeError(f"MAF invoke {server}.{tool} failed ({resp.status_code}): {detail}")
    body = resp.json()
    if isinstance(body, dict) and "result" in body:
        return body["result"]
    return body


async def catalog_tools() -> dict[str, Any]:
    url = f"{maf_base_url()}/tools"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {"ok": False, "payload": payload}


async def maf_health() -> dict[str, Any]:
    url = f"{maf_base_url()}/ask/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        payload = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {"ok": resp.status_code < 400, "status_code": resp.status_code}
        )
        if isinstance(payload, dict):
            return {**payload, "mode": "proxy", "maf_base_url": maf_base_url()}
        return {"ok": True, "mode": "proxy", "maf_base_url": maf_base_url(), "payload": payload}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "orchestrator": "maf",
            "mode": "proxy",
            "maf_base_url": maf_base_url(),
            "error": str(exc),
        }
