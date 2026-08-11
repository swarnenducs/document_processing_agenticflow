"""LangGraph shared state for the voice → contract agent."""

from __future__ import annotations

from typing import Any, TypedDict


class VoiceContractState(TypedDict, total=False):
    """State passed between LangGraph voice-contract nodes."""

    # Inputs
    transcript: str
    auto_create: bool
    thread_id: str
    output_dir: str

    # Parsed request
    intent: str | None
    legal_entity_name: str | None
    contract_reference_number: str | None

    # Lookups (API / SQLite)
    legal_entity: dict[str, Any] | None
    pricelist: dict[str, Any] | None
    candidates: list[dict[str, Any]]

    # HITL
    confirmation: dict[str, Any] | None
    confirmed: bool

    # Outputs
    contract_payload: dict[str, Any] | None
    contract_file: str | None
    contract_text_file: str | None
    contract_text: str | None
    contract_id: str | None

    # Control / messaging
    status: str  # running | needs_confirmation | completed | rejected
    ok: bool
    message: str
    errors: list[str]
