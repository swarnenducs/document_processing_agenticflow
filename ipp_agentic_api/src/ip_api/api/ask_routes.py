"""Thin API entry: POST /api/ask → MAF HTTP service."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from ip_api.services.maf_client import central_agent_endpoint
from ip_api.services.session_service import ensure_request_session

router = APIRouter(tags=["maf"])


class AskRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    prompt: str | None = Field(
        default=None,
        validation_alias=AliasChoices("Prompt", "prompt", "message"),
        description="User question for the LLM",
    )
    persona: str | None = Field(
        default=None,
        validation_alias=AliasChoices("Persona", "persona", "role"),
        description="Persona definition from the request (scope and prohibitions)",
    )
    instructions: str | None = Field(
        default=None,
        description="Optional system instructions override for this request",
    )
    session_id: str | None = Field(default=None, description="Reuse existing session")
    user_id: str | None = None
    user_email: str | None = None

    @model_validator(mode="after")
    def _need_prompt(self) -> AskRequest:
        if not (self.prompt or "").strip():
            raise ValueError("Provide Prompt")
        if not (self.persona or "").strip():
            raise ValueError("Provide Persona")
        return self


class AskResponse(BaseModel):
    ok: bool = Field(default=True, description="False if the orchestrator reported failure")
    text: str = Field(description="Assistant reply")
    response_id: str | None = Field(default=None, description="MAF response id when present")
    orchestrator: str = Field(default="maf", description="Always maf for this route")
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    role: str | None = None
    persona: str | None = None
    prompt: str | None = None
    version: str | None = None
    authorized: bool | None = None
    validation: dict[str, Any] | None = None


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Chat: proxy to MAF /ask",
)
async def ask(body: AskRequest) -> AskResponse:
    """
    Natural-language question for the MAF orchestrator (tools/chat).

    Send `Prompt` + `Persona` (definition text). An LLM validator checks the
    prompt against that definition; confidence must meet
    ``MAF_PERSONA_VALIDATOR_MIN_CONFIDENCE`` (default 0.95) before execute.
    Needs MAF at `CENTRAL_AGENT_END_POINT` (default `http://127.0.0.1:8003`).
    **Not** used for document jobs — those are `POST /api/v1/documents/jobs`.
    """
    from ip_api.flow_debug import flow_breakpoint

    flow_breakpoint("api_ask", message=body.prompt, session_id=body.session_id)
    session = ensure_request_session(
        request_kind="maf",
        session_id=body.session_id,
        user_id=body.user_id,
        user_email=body.user_email,
        path="/api/ask",
    )

    url = f"{central_agent_endpoint()}/ask"
    payload = {
        "Prompt": body.prompt,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "user_email": session.user_email,
    }
    if body.instructions is not None:
        payload["instructions"] = body.instructions
    if body.persona is not None:
        payload["Persona"] = body.persona
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
        ok=bool(data.get("ok", data.get("authorized", True))),
        text=str(data.get("text", "")),
        response_id=data.get("response_id"),
        session_id=data.get("session_id") or session.session_id,
        user_id=data.get("user_id") or session.user_id,
        user_email=data.get("user_email") or session.user_email,
        role=data.get("role") or data.get("persona") or body.persona,
        persona=data.get("persona") or body.persona,
        prompt=data.get("prompt") or data.get("Prompt") or body.prompt,
        version=data.get("version"),
        authorized=data.get("authorized"),
        validation=data.get("validation"),
    )


@router.get("/ask/prompts", summary="MAF prompt files and min confidence")
async def list_ask_prompts() -> dict[str, Any]:
    """Validator/orchestrator paths and ``min_confidence`` from MAF config."""
    url = f"{central_agent_endpoint()}/prompts"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MAF service unreachable at {url}: {exc}",
        ) from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/ask/health", summary="MAF /ask/health via proxy")
async def ask_health() -> dict[str, Any]:
    """Whether the chat proxy can reach MAF. **503** if MAF is down."""
    from ip_api.services.maf_client import maf_health

    return await maf_health()
