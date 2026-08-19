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
    """Ping MCPs via the central agent catalogue."""
    catalog = await maf_client.catalog_tools()
    return {
        "ok": bool(catalog.get("ok")),
        "orchestrator": "maf",
        **catalog,
    }


@router.get("/tools")
async def all_mcp_tools() -> dict[str, Any]:
    """List tools from every MCP registered on MAF."""
    try:
        return await maf_client.catalog_tools()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"central agent unavailable: {exc}") from exc


@router.get("/document/tools")
async def document_tools() -> dict[str, Any]:
    catalog = await maf_client.catalog_tools()
    block = catalog.get("contract_autocreation_mcp") or catalog.get("document_process_mcp") or {}
    if not block:
        raise HTTPException(status_code=503, detail="document MCP not registered on MAF")
    return {"mcp": "contract_autocreation_mcp", "via": "maf", **block}


@router.post("/document/generate")
async def document_generate_via_mcp(body: DocumentGenerateRequest) -> dict[str, Any]:
    """FastAPI → MAF → contract_autocreation_mcp ``generate_document``."""
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


@router.get("/voice/tools")
async def voice_tools() -> dict[str, Any]:
    catalog = await maf_client.catalog_tools()
    block = catalog.get("voice_process_mcp") or {}
    if not block:
        raise HTTPException(status_code=503, detail="voice MCP not registered on MAF")
    return {"mcp": "voice_process_mcp", "via": "maf", **block}


@router.post("/voice/contract")
async def voice_contract_via_mcp(body: VoiceStartRequest) -> dict[str, Any]:
    """FastAPI → MAF → voice_process_mcp ``start_voice_contract``."""
    try:
        return await maf_client.invoke_tool("voice", "start_voice_contract", body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice call failed: {exc}") from exc


@router.post("/voice/contract/confirm")
async def voice_confirm_via_mcp(body: VoiceConfirmRequest) -> dict[str, Any]:
    """FastAPI → MAF → voice_process_mcp ``confirm_voice_contract``."""
    try:
        return await maf_client.invoke_tool(
            "voice", "confirm_voice_contract", body.model_dump(exclude_none=True)
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"central agent voice confirm failed: {exc}") from exc
