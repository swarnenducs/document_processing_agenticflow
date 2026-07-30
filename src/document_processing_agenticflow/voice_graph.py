"""LangGraph agent graph for voice → contract (HITL via interrupt)."""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from document_processing_agenticflow.models.voice_state import VoiceContractState
from document_processing_agenticflow.nodes.voice_contract import (
    await_confirmation_node,
    fetch_legal_entity_node,
    fetch_pricelist_node,
    generate_contract_node,
    parse_intent_node,
    route_after_confirm,
    route_after_lookup,
    route_after_parse,
)
from document_processing_agenticflow.services.voice_contract_workflow import VoiceContractResult

# Process-local checkpointer so HITL resume works across chat turns.
_CHECKPOINTER = MemorySaver()
_GRAPH = None


def build_voice_contract_graph(*, checkpointer: MemorySaver | None = None):
    """
    Voice contract LangGraph agent:

      START → parse_intent → fetch_legal_entity → fetch_pricelist
            → await_confirmation (interrupt HITL)
            → generate_contract → END

    Lookups use SQLite today (nodes can swap to HTTP APIs). Persist to
    SQLite/files is done by the API layer after the graph completes.
    """
    graph = StateGraph(VoiceContractState)

    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("fetch_legal_entity", fetch_legal_entity_node)
    graph.add_node("fetch_pricelist", fetch_pricelist_node)
    graph.add_node("await_confirmation", await_confirmation_node)
    graph.add_node("generate_contract", generate_contract_node)

    graph.add_edge(START, "parse_intent")
    graph.add_conditional_edges(
        "parse_intent",
        route_after_parse,
        {"continue": "fetch_legal_entity", "stop": END},
    )
    graph.add_conditional_edges(
        "fetch_legal_entity",
        route_after_lookup,
        {"continue": "fetch_pricelist", "stop": END},
    )
    graph.add_conditional_edges(
        "fetch_pricelist",
        route_after_lookup,
        {"continue": "await_confirmation", "stop": END},
    )
    graph.add_conditional_edges(
        "await_confirmation",
        route_after_confirm,
        {"continue": "generate_contract", "stop": END},
    )
    graph.add_edge("generate_contract", END)

    return graph.compile(checkpointer=checkpointer or _CHECKPOINTER)


def get_voice_contract_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_voice_contract_graph()
    return _GRAPH


def _state_to_result(state: dict[str, Any], *, thread_id: str | None = None) -> VoiceContractResult:
    entity = state.get("legal_entity")
    status = state.get("status") or "rejected"
    interrupts = state.get("__interrupt__") or []
    if interrupts and status != "completed":
        payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        if isinstance(payload, dict):
            return VoiceContractResult(
                ok=False,
                status="needs_confirmation",
                message=str(payload.get("message") or "Confirmation required."),
                intent=state.get("intent") or "create_contract",
                legal_entity_name=state.get("legal_entity_name"),
                contract_reference_number=str(
                    payload.get("suggested_ref") or state.get("contract_reference_number") or ""
                )
                or None,
                legal_entity=payload.get("legal_entity") or entity,
                pricelist=state.get("pricelist"),
                candidates=list(payload.get("candidates") or state.get("candidates") or []),
                transcript=state.get("transcript"),
                spoken_name=state.get("legal_entity_name"),
                spoken_number=str(
                    payload.get("suggested_ref") or state.get("contract_reference_number") or ""
                )
                or None,
                contact=payload.get("legal_entity") or entity,
                contract_id=thread_id,  # temporary; overwritten by real id on complete
            )

    return VoiceContractResult(
        ok=bool(state.get("ok")),
        status=status,
        message=str(state.get("message") or ""),
        intent=state.get("intent"),
        legal_entity_name=state.get("legal_entity_name"),
        contract_reference_number=state.get("contract_reference_number"),
        legal_entity=entity,
        pricelist=state.get("pricelist"),
        candidates=list(state.get("candidates") or []),
        contract_payload=state.get("contract_payload"),
        contract_file=state.get("contract_file"),
        contract_text_file=state.get("contract_text_file"),
        contract_text=state.get("contract_text"),
        contract_id=state.get("contract_id"),
        transcript=state.get("transcript"),
        spoken_name=state.get("legal_entity_name")
        or (entity or {}).get("code")
        or (entity or {}).get("legalName"),
        spoken_number=state.get("contract_reference_number"),
        contact=entity,
    )


def start_voice_contract_agent(
    transcript: str,
    *,
    auto_create: bool = False,
    thread_id: str | None = None,
    output_dir: str | None = None,
) -> tuple[VoiceContractResult, str]:
    """
    Start (or continue from START) the LangGraph voice-contract agent.

    Returns (result, thread_id). When HITL is required, status=needs_confirmation
    and the caller must resume with ``resume_voice_contract_agent``.
    """
    graph = get_voice_contract_graph()
    tid = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": tid}}
    out = graph.invoke(
        {
            "transcript": transcript,
            "auto_create": auto_create,
            "thread_id": tid,
            **({"output_dir": output_dir} if output_dir else {}),
        },
        config=config,
    )
    result = _state_to_result(out, thread_id=tid)
    result.thread_id = tid
    # Expose LangGraph thread id for resume (not the SQLite contract id yet)
    if result.status == "needs_confirmation":
        result.contract_id = None
    return result, tid


def resume_voice_contract_agent(
    thread_id: str,
    *,
    user_text: str | None = None,
    action: str | None = None,
    contract_reference_number: str | None = None,
) -> VoiceContractResult:
    """Resume HITL interrupt with user confirmation / selected reference."""
    graph = get_voice_contract_graph()
    config = {"configurable": {"thread_id": thread_id}}
    resume_payload: dict[str, Any] = {
        "action": action or user_text or "",
        "text": user_text or action or "",
        "ref": contract_reference_number or "",
    }
    out = graph.invoke(Command(resume=resume_payload), config=config)
    result = _state_to_result(out, thread_id=thread_id)
    result.thread_id = thread_id
    return result


# Module-level compiled graph for LangGraph Studio / langgraph.dev
app = build_voice_contract_graph()
