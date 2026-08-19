"""Pydantic payloads for voice FastMCP tools (structured JSON)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class McpHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    mcp: str
    agent: str
    transport: str = "http|stdio"
    host: str | None = None
    port: int | None = None


class VoiceContractMcpResponse(BaseModel):
    """Public MCP result for start/confirm voice contract."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str
    mcp: str = "voice_process_mcp"
    intent: str | None = None
    status: str = "rejected"
    legal_entity_name: str | None = None
    contract_reference_number: str | None = None
    legal_entity: dict[str, Any] | None = None
    pricelist: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    contract_payload: dict[str, Any] | None = None
    contract_file: str | None = None
    contract_text_file: str | None = None
    contract_text: str | None = None
    transcript: str | None = None
    contract_id: str | None = None
    thread_id: str | None = None
    spoken_name: str | None = None
    spoken_number: str | None = None
    contact: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)

    @classmethod
    def from_workflow(cls, result: Any, *, mcp: str, contract_id: str | None = None) -> VoiceContractMcpResponse:
        data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        data["mcp"] = mcp
        if contract_id:
            data["contract_id"] = contract_id
        return cls.model_validate(data)


class VoiceContractListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcp: str = "voice_process_mcp"
    count: int = 0
    contracts: list[dict[str, Any]] = Field(default_factory=list)
