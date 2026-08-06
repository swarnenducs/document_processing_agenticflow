"""FastAPI routes that communicate with document_process_mcp + voice_process_mcp."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from document_processing_agenticflow.mcp.client import (
    get_document_mcp_client,
    get_voice_mcp_client,
)

router = APIRouter(prefix="/agents", tags=["mcp-agents"])


class DocumentGenerateRequest(BaseModel):
    template_path: str = Field(..., description="Path to Word .docx template")
    data_path: str | None = Field(default=None, description="Path to JSON data file")
    data_json: str | None = Field(
        default=None,
        description="Inline JSON object string (alternative to data_path)",
    )
    output_path: str | None = None
    skip_validation: bool = False
    skip_extraction_validation: bool = False
    max_retries: int = 1
    validation_threshold: float = 0.7


class VoiceStartRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    auto_create: bool = False


class VoiceConfirmRequest(BaseModel):
    legal_entity: str = Field(..., min_length=1)
    contract_reference_number: str = Field(..., min_length=1)
    thread_id: str | None = None
    user_text: str = "yes"
    transcript: str | None = None


@router.get("/health")
async def agents_health() -> dict[str, Any]:
    """Ping document_process_mcp + voice_process_mcp."""
    doc = await get_document_mcp_client().health()
    voice = await get_voice_mcp_client().health()
    return {
        "ok": bool(doc.get("ok")) and bool(voice.get("ok")),
        "document_process_mcp": doc,
        "voice_process_mcp": voice,
    }


@router.get("/document/tools")
async def document_tools() -> dict[str, Any]:
    try:
        tools = await get_document_mcp_client().list_tools()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"document_process_mcp unavailable: {exc}") from exc
    return {"mcp": "document_process_mcp", "tools": tools}


@router.post("/document/generate")
async def document_generate_via_mcp(body: DocumentGenerateRequest) -> dict[str, Any]:
    """FastAPI → document_process_mcp ``generate_document`` tool."""
    if not body.data_path and not body.data_json:
        raise HTTPException(status_code=400, detail="Provide data_path or data_json")
    try:
        return await get_document_mcp_client().call_tool(
            "generate_document",
            body.model_dump(exclude_none=True),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"document_process_mcp call failed: {exc}") from exc


@router.get("/voice/tools")
async def voice_tools() -> dict[str, Any]:
    try:
        tools = await get_voice_mcp_client().list_tools()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"voice_process_mcp unavailable: {exc}") from exc
    return {"mcp": "voice_process_mcp", "tools": tools}


@router.post("/voice/contract")
async def voice_contract_via_mcp(body: VoiceStartRequest) -> dict[str, Any]:
    """FastAPI → voice_process_mcp ``start_voice_contract`` tool."""
    try:
        return await get_voice_mcp_client().call_tool(
            "start_voice_contract",
            body.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"voice_process_mcp call failed: {exc}") from exc


@router.post("/voice/contract/confirm")
async def voice_confirm_via_mcp(body: VoiceConfirmRequest) -> dict[str, Any]:
    """FastAPI → voice_process_mcp ``confirm_voice_contract`` tool."""
    try:
        return await get_voice_mcp_client().call_tool(
            "confirm_voice_contract",
            body.model_dump(exclude_none=True),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"voice_process_mcp call failed: {exc}") from exc
