"""Thin API entry: POST /api/ask → MAF HTTP service."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ip_api.services.maf_client import central_agent_endpoint
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
    ok: bool = Field(default=True, description="False if the orchestrator reported failure")
    text: str = Field(description="Assistant reply")
    response_id: str | None = Field(default=None, description="MAF response id when present")
    orchestrator: str = Field(default="maf", description="Always maf for this route")
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Chat: proxy to MAF /ask",
)
async def ask(body: AskRequest) -> AskResponse:
    """
    Natural-language question for the MAF orchestrator (tools/chat).

    Needs MAF at `CENTRAL_AGENT_END_POINT` (default `http://127.0.0.1:8003`).
    **Not** used for document jobs — those are `POST /api/v1/documents/jobs`.
    """
    from ip_api.flow_debug import flow_breakpoint

    flow_breakpoint("api_ask", message=body.message, session_id=body.session_id)
    session = ensure_request_session(
        request_kind="maf",
        session_id=body.session_id,
        user_id=body.user_id,
        user_email=body.user_email,
        path="/api/ask",
    )

    url = f"{central_agent_endpoint()}/ask"
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


@router.get("/ask/health", summary="MAF /ask/health via proxy")
async def ask_health() -> dict[str, Any]:
    """Whether the chat proxy can reach MAF. **503** if MAF is down."""
    from ip_api.services.maf_client import maf_health

    return await maf_health()
