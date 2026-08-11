"""Thin API entry: POST /api/ask → MAF service (or embedded orchestrator)."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ip_api.services.session_service import ensure_request_session

router = APIRouter(tags=["maf"])


class AskRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Natural-language ask for the MAF orchestrator")
    instructions: str | None = Field(
        default=None,
        description="Optional system instructions override for this request",
    )
    session_id: str | None = Field(default=None, description="Reuse existing session")
    user_id: str | None = None
    user_email: str | None = None


class AskResponse(BaseModel):
    ok: bool = True
    text: str
    response_id: str | None = None
    orchestrator: str = "maf"
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None


def _maf_base_url() -> str:
    return (os.getenv("MAF_BASE_URL") or os.getenv("MAF_URL") or "http://127.0.0.1:8003").rstrip("/")


def _maf_embedded() -> bool:
    return (os.getenv("MAF_EMBEDDED", "false") or "").strip().lower() in {"1", "true", "yes", "on"}


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
    """Proxy to standalone MAF service, or run embedded when MAF_EMBEDDED=true."""
    session = ensure_request_session(
        request_kind="maf",
        session_id=body.session_id,
        user_id=body.user_id,
        user_email=body.user_email,
        path="/api/ask",
    )

    if _maf_embedded():
        from central_agentic_flow.orchestrator import ask_maf

        try:
            result = await ask_maf(body.message, instructions=body.instructions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"MAF ask failed: {exc}") from exc
        return AskResponse(
            text=result.text,
            response_id=result.response_id,
            session_id=session.session_id,
            user_id=session.user_id,
            user_email=session.user_email,
        )

    url = f"{_maf_base_url()}/ask"
    payload = {
        "message": body.message,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "user_email": session.user_email,
    }
    if body.instructions is not None:
        payload["instructions"] = body.instructions
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("MAF_PROXY_TIMEOUT", "320"))) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MAF service unreachable at {url}: {exc}",
        ) from exc
    if resp.status_code >= 400:
        detail: Any
        try:
            detail = resp.json()
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    data = resp.json()
    return AskResponse(
        text=str(data.get("text", "")),
        response_id=data.get("response_id"),
        session_id=data.get("session_id") or session.session_id,
        user_id=data.get("user_id") or session.user_id,
        user_email=data.get("user_email") or session.user_email,
    )


@router.get("/ask/health")
async def ask_health() -> dict[str, Any]:
    """Readiness: proxy MAF /ask/health (or embedded client resolve)."""
    if _maf_embedded():
        try:
            from central_agentic_flow.orchestrator import (
                document_mcp_url,
                resolve_maf_chat_client,
                voice_mcp_url,
            )

            client = resolve_maf_chat_client()
            return {
                "ok": True,
                "orchestrator": "maf",
                "mode": "embedded",
                "chat_client": type(client).__name__,
                "document_mcp_url": document_mcp_url(),
                "voice_mcp_url": voice_mcp_url(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "orchestrator": "maf", "mode": "embedded", "error": str(exc)}

    url = f"{_maf_base_url()}/ask/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
        }
        if isinstance(payload, dict):
            return {**payload, "mode": "proxy", "maf_base_url": _maf_base_url()}
        return {"ok": True, "mode": "proxy", "maf_base_url": _maf_base_url(), "payload": payload}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "orchestrator": "maf",
            "mode": "proxy",
            "maf_base_url": _maf_base_url(),
            "error": str(exc),
        }
