"""FastAPI routes that communicate with MCP tools **through MAF only**."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ip_api.services import maf_client

router = APIRouter(prefix="/agents", tags=["mcp-agents"])


class DocumentGenerateRequest(BaseModel):
    template_path: str = Field(
        ...,
        description="Local path or Azure Blob ref (blob://container/jobs/{id}/upload/template.docx)",
    )
    data_path: str | None = Field(
        default=None,
        description="Local path or Azure Blob ref to JSON data",
    )
    data_json: str | None = Field(
        default=None,
        description="Inline JSON object string (alternative to data_path)",
    )
    output_path: str | None = None
    job_id: str | None = Field(
        default=None,
        description="If set, Document MCP updates document_jobs + accuracy in SQL",
    )
    xid: str | None = None
    skip_validation: bool = False
    skip_extraction_validation: bool = False
    max_retries: int | None = Field(
        default=None,
        ge=0,
        le=3,
        description="Overrides DOCUMENT_MAX_RETRIES when set",
    )
    validation_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Overrides DOCUMENT_VALIDATION_THRESHOLD when set",
    )
    optimized_flow: bool | None = Field(
        default=None,
        description="Use llm_optimization.json mapper cascade when true",
    )


class VoiceStartRequest(BaseModel):
    transcript: str = Field(
        ...,
        min_length=1,
        description="Spoken or typed instruction, e.g. create contract with legal entity AVC …",
    )
    auto_create: bool = Field(
        default=False,
        description="Skip HITL confirmation when true",
    )


class VoiceConfirmRequest(BaseModel):
    legal_entity: str = Field(..., min_length=1, description="Entity code or name, e.g. AVC")
    contract_reference_number: str = Field(..., min_length=1, description="e.g. CR-1001")
    thread_id: str | None = Field(default=None, description="From start response")
    user_text: str = Field(default="yes", description="Operator reply")
    transcript: str | None = None


@router.get("/health", summary="MAF catalogue ping")
async def agents_health() -> dict[str, Any]:
    """Whether MAF answered and which MCP servers it registered. Requires MAF up."""
    catalog = await maf_client.catalog_tools()
    return {
        "ok": bool(catalog.get("ok")),
        "orchestrator": "maf",
        **catalog,
    }


@router.get("/tools", summary="List all MCP tools on MAF")
async def all_mcp_tools() -> dict[str, Any]:
    """Tool names from every MCP registered on the central agent."""
    try:
        return await maf_client.catalog_tools()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"central agent unavailable: {exc}") from exc


@router.get("/document/tools", summary="Document MCP tools only")
async def document_tools() -> dict[str, Any]:
    """Subset of `/tools` for the document / contract-autocreation MCP."""
    catalog = await maf_client.catalog_tools()
    block = catalog.get("contract_autocreation_mcp") or catalog.get("document_process_mcp") or {}
    if not block:
        raise HTTPException(status_code=503, detail="document MCP not registered on MAF")
    return {"mcp": "contract_autocreation_mcp", "via": "maf", **block}


@router.post("/document/generate", summary="Generate via MAF (paths, not upload)")
async def document_generate_via_mcp(body: DocumentGenerateRequest) -> dict[str, Any]:
    """
    FastAPI → MAF → `generate_document`. Body uses **paths already on the MCP host**
    (`template_path`, `data_path` or `data_json`). For file upload use
    `POST /api/v1/documents/jobs` instead.
    """
    from ip_api.flow_debug import flow_breakpoint

    flow_breakpoint("document_generate_via_mcp", template_path=body.template_path)
    if not body.data_path and not body.data_json:
        raise HTTPException(status_code=400, detail="Provide data_path or data_json")
    try:
        return await maf_client.invoke_tool(
            "document", "generate_document", body.model_dump(exclude_none=True)
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent document call failed: {exc}") from exc


@router.get("/voice/tools", summary="Voice MCP tools only")
async def voice_tools() -> dict[str, Any]:
    """Subset of `/tools` for voice_process_mcp."""
    catalog = await maf_client.catalog_tools()
    block = catalog.get("voice_process_mcp") or {}
    if not block:
        raise HTTPException(status_code=503, detail="voice MCP not registered on MAF")
    return {"mcp": "voice_process_mcp", "via": "maf", **block}


@router.post("/voice/contract", summary="Start voice contract via MAF tools")
async def voice_contract_via_mcp(body: VoiceStartRequest) -> dict[str, Any]:
    """Same as `POST /api/v1/voice/contract` but raw MCP payload (no session wrapper)."""
    try:
        return await maf_client.invoke_tool("voice", "start_voice_contract", body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice call failed: {exc}") from exc


@router.post("/voice/contract/confirm", summary="Confirm voice contract via MAF tools")
async def voice_confirm_via_mcp(body: VoiceConfirmRequest) -> dict[str, Any]:
    """Same as `POST /api/v1/voice/contract/confirm` via MAF `confirm_voice_contract`."""
    try:
        return await maf_client.invoke_tool(
            "voice", "confirm_voice_contract", body.model_dump(exclude_none=True)
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice confirm failed: {exc}") from exc
