"""LangGraph nodes for voice → contract agent (lookups via SQLite/API helpers)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from document_processing_agenticflow.models.voice_state import VoiceContractState
from document_processing_agenticflow.services.voice_contract_workflow import (
    _IRRELEVANT_MSG,
    _is_create_contract_intent,
    extract_legal_entity_and_reference,
    finalize_contract,
    format_contract_ref,
    is_confirmation,
)


def _store():
    from document_processing_agenticflow.storage.job_store import JobStore

    return JobStore()


def parse_intent_node(state: VoiceContractState) -> dict[str, Any]:
    text = " ".join((state.get("transcript") or "").strip().split())
    if not text:
        return {
            "status": "rejected",
            "ok": False,
            "message": _IRRELEVANT_MSG,
            "intent": None,
            "transcript": state.get("transcript") or "",
            "errors": ["empty transcript"],
        }

    if not _is_create_contract_intent(text):
        return {
            "status": "rejected",
            "ok": False,
            "message": _IRRELEVANT_MSG,
            "intent": "unsupported",
            "transcript": text,
            "errors": ["unsupported intent"],
        }

    entity_name, contract_ref = extract_legal_entity_and_reference(text)
    if not entity_name or not contract_ref:
        return {
            "status": "rejected",
            "ok": False,
            "intent": "create_contract",
            "transcript": text,
            "legal_entity_name": entity_name,
            "contract_reference_number": contract_ref,
            "message": (
                "Create-contract request detected, but Legal entity and contract "
                "reference number are required. Example: "
                '"please create contract with legal entity AVC contract reference '
                'number CR 1001".'
            ),
            "errors": ["missing entity or reference"],
        }

    return {
        "status": "running",
        "ok": False,
        "intent": "create_contract",
        "transcript": text,
        "legal_entity_name": entity_name,
        "contract_reference_number": contract_ref,
        "message": "Intent parsed; fetching legal entity.",
        "errors": [],
    }


def fetch_legal_entity_node(state: VoiceContractState) -> dict[str, Any]:
    """Node that can call SQLite / future HTTP API for legal entity master data."""
    store = _store()
    store.ensure_contract_catalog_seeded()
    name = state.get("legal_entity_name") or ""
    entity = store.find_legal_entity(name)
    if entity is None:
        return {
            "status": "rejected",
            "ok": False,
            "legal_entity": None,
            "message": f"No legal entity found for '{name}'. {_IRRELEVANT_MSG}",
            "errors": [f"legal entity not found: {name}"],
        }
    return {
        "legal_entity": entity,
        "message": f"Legal entity loaded: {entity.get('legalName')}",
        "status": "running",
    }


def fetch_pricelist_node(state: VoiceContractState) -> dict[str, Any]:
    """Node that fetches pricelist by contract reference (SQLite / future API)."""
    store = _store()
    store.ensure_contract_catalog_seeded()
    entity = state.get("legal_entity") or {}
    ref = state.get("contract_reference_number") or ""
    entity_code = str(entity.get("code") or "") or None

    matches = store.search_pricelists(ref, legal_entity_code=entity_code)
    if not matches:
        matches = store.search_pricelists(ref)
    if not matches:
        return {
            "status": "rejected",
            "ok": False,
            "pricelist": None,
            "candidates": [],
            "message": f"No pricelist found near reference '{ref}'. {_IRRELEVANT_MSG}",
            "errors": [f"pricelist not found: {ref}"],
        }

    entity_code_u = str(entity.get("code") or "").upper()
    entity_matches = [
        m for m in matches if str(m.get("legalEntityCode") or "").upper() == entity_code_u
    ]
    candidates = entity_matches or matches
    best = candidates[0]
    pretty_ref = format_contract_ref(str(best.get("contractReferenceNumber") or ref))
    return {
        "candidates": candidates,
        "pricelist": best,
        "contract_reference_number": pretty_ref,
        "message": f"Pricelist candidates found for {pretty_ref}",
        "status": "running",
    }


def await_confirmation_node(state: VoiceContractState) -> dict[str, Any]:
    """Human-in-the-loop gate via LangGraph interrupt()."""
    if state.get("auto_create"):
        return {
            "confirmed": True,
            "confirmation": {"action": "auto", "ref": state.get("contract_reference_number")},
            "status": "running",
            "message": "Auto-create enabled; skipping human confirmation.",
        }

    entity = state.get("legal_entity") or {}
    candidates = state.get("candidates") or []
    pretty_ref = state.get("contract_reference_number")
    options = ", ".join(
        format_contract_ref(str(c.get("contractReferenceNumber") or "")) for c in candidates
    )
    prompt = (
        f"I found legal entity **{entity.get('legalName')}** ({entity.get('code')}) "
        f"and matching contract reference **{pretty_ref}**"
        + (f" (also: {options})." if len(candidates) > 1 else ".")
        + " Reply **yes** / **confirm** or type the reference "
        f"(e.g. `{pretty_ref}`) to create the dummy contract."
    )

    decision = interrupt(
        {
            "type": "confirm_contract",
            "message": prompt,
            "legal_entity": entity,
            "candidates": candidates,
            "suggested_ref": pretty_ref,
            "thread_id": state.get("thread_id"),
        }
    )

    # Resume payload from Command(resume=...)
    if isinstance(decision, dict):
        action = str(decision.get("action") or decision.get("text") or "").strip()
        ref = str(decision.get("ref") or decision.get("contract_reference_number") or "").strip()
    else:
        action = str(decision or "").strip()
        ref = ""

    if is_confirmation(action) and not ref:
        ref = str(pretty_ref or "")
    elif not ref:
        ref = format_contract_ref(action)

    # Re-resolve pricelist for chosen ref
    store = _store()
    entity_code = str(entity.get("code") or "") or None
    matches = store.search_pricelists(ref, legal_entity_code=entity_code) or store.search_pricelists(
        ref
    )
    if not matches:
        return {
            "confirmed": False,
            "confirmation": {"action": action, "ref": ref},
            "status": "rejected",
            "ok": False,
            "message": f"No pricelist found for reference '{ref}'. {_IRRELEVANT_MSG}",
            "errors": [f"confirmation ref not found: {ref}"],
        }

    chosen = matches[0]
    # Prefer entity-matching candidate
    if entity_code:
        for m in matches:
            if str(m.get("legalEntityCode") or "").upper() == entity_code.upper():
                chosen = m
                break

    return {
        "confirmed": True,
        "confirmation": {"action": action, "ref": ref},
        "pricelist": chosen,
        "contract_reference_number": format_contract_ref(
            str(chosen.get("contractReferenceNumber") or ref)
        ),
        "status": "running",
        "message": f"Confirmation accepted for {format_contract_ref(ref)}",
    }


def generate_contract_node(state: VoiceContractState) -> dict[str, Any]:
    store = _store()
    entity = state.get("legal_entity") or {}
    pricelist = state.get("pricelist") or {}
    out_dir = state.get("output_dir")
    result = finalize_contract(
        entity=entity,
        pricelist=pricelist,
        store=store,
        transcript=state.get("transcript"),
        output_dir=Path(out_dir) if out_dir else None,
    )
    return {
        "contract_payload": result.contract_payload,
        "contract_file": result.contract_file,
        "contract_text_file": result.contract_text_file,
        "contract_text": result.contract_text,
        "ok": True,
        "status": "completed",
        "message": result.message,
    }


def persist_contract_node(state: VoiceContractState) -> dict[str, Any]:
    """Persist accepted contract metadata (SQLite). File move can happen in API layer."""
    store = _store()
    entity = state.get("legal_entity") or {}
    saved = store.save_voice_contract(
        spoken_name=str(entity.get("code") or entity.get("legalName") or state.get("legal_entity_name") or ""),
        spoken_number=str(state.get("contract_reference_number") or ""),
        contact=entity,
        legal_entity=entity,
        pricelist=state.get("pricelist"),
        contract_payload=state.get("contract_payload"),
        contract_file=state.get("contract_file"),
        transcript=state.get("transcript"),
    )
    return {
        "contract_id": saved.get("contract_id"),
        "message": (
            f"{state.get('message') or 'Contract created.'} "
            f"Saved to SQLite as contract `{saved.get('contract_id')}`."
        ),
        "ok": True,
        "status": "completed",
    }


def route_after_parse(state: VoiceContractState) -> str:
    return "stop" if state.get("status") == "rejected" else "continue"


def route_after_lookup(state: VoiceContractState) -> str:
    return "stop" if state.get("status") == "rejected" else "continue"


def route_after_confirm(state: VoiceContractState) -> str:
    if state.get("status") == "rejected" or not state.get("confirmed"):
        return "stop"
    return "continue"
