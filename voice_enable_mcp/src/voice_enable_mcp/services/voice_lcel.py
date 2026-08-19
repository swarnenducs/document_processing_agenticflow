"""Voice transcript/confirmation via LCEL, with regex fallback when no LLM."""

from __future__ import annotations

from pydantic import BaseModel, Field

from voice_enable_mcp.services.trace_log import traced_invoke
from voice_enable_mcp.services.voice_contract_workflow import (
    extract_legal_entity_and_reference,
    format_contract_ref,
    is_confirmation,
    _is_create_contract_intent,
)


class VoiceIntentPayload(BaseModel):
    create_contract: bool = False
    legal_entity_name: str = ""
    contract_reference_number: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = ""


class VoiceConfirmPayload(BaseModel):
    confirmed: bool = False
    contract_reference_number: str = ""
    notes: str = ""


def _mapper_llm(schema: type):
    from voice_enable_mcp.services.llm_factory import MapperLLM, is_mapper_available

    if not is_mapper_available():
        return None, None
    mapper = MapperLLM(structured_schema=schema)
    return mapper.as_tuple()


def parse_voice_transcript(text: str) -> VoiceIntentPayload:
    """Prefer LCEL structured parse; fall back to regex if LLM is off or fails."""
    cleaned = " ".join((text or "").strip().split())
    regex = _regex_intent(cleaned)
    try:
        llm, config = _mapper_llm(VoiceIntentPayload)
        if llm is None:
            return regex
        from voice_enable_mcp.services.prompts import build_intent_chain

        chain = build_intent_chain(llm)
        result: VoiceIntentPayload = traced_invoke(
            chain,
            {"transcript": cleaned},
            role="voice_intent",
            provider=config.provider,
            model=config.model,
        )
        entity = (result.legal_entity_name or "").strip()
        ref = (result.contract_reference_number or "").strip()
        if result.create_contract and (not entity or not ref):
            entity = entity or (regex.legal_entity_name or "")
            ref = ref or (regex.contract_reference_number or "")
        return VoiceIntentPayload(
            create_contract=bool(result.create_contract),
            legal_entity_name=entity,
            contract_reference_number=ref,
            confidence=float(result.confidence or 0.0),
            notes=result.notes or "",
        )
    except Exception:  # noqa: BLE001 — keep voice usable without LLM
        return regex


def interpret_voice_confirmation(
    user_text: str,
    *,
    suggested_ref: str | None,
) -> VoiceConfirmPayload:
    suggested = (suggested_ref or "").strip()
    regex = _regex_confirm(user_text, suggested)
    try:
        llm, config = _mapper_llm(VoiceConfirmPayload)
        if llm is None:
            return regex
        from voice_enable_mcp.services.prompts import build_confirm_chain

        chain = build_confirm_chain(llm)
        result: VoiceConfirmPayload = traced_invoke(
            chain,
            {"user_text": user_text or "", "suggested_ref": suggested},
            role="voice_confirm",
            provider=config.provider,
            model=config.model,
        )
        ref = (result.contract_reference_number or "").strip() or suggested
        return VoiceConfirmPayload(
            confirmed=bool(result.confirmed),
            contract_reference_number=ref,
            notes=result.notes or "",
        )
    except Exception:  # noqa: BLE001
        return regex


def _regex_intent(text: str) -> VoiceIntentPayload:
    if not text or not _is_create_contract_intent(text):
        return VoiceIntentPayload(create_contract=False)
    entity, ref = extract_legal_entity_and_reference(text)
    return VoiceIntentPayload(
        create_contract=True,
        legal_entity_name=entity or "",
        contract_reference_number=ref or "",
        confidence=0.9 if entity and ref else 0.4,
        notes="regex",
    )


def _regex_confirm(user_text: str, suggested: str) -> VoiceConfirmPayload:
    action = (user_text or "").strip()
    ref = ""
    if is_confirmation(action):
        ref = suggested
        confirmed = True
    else:
        ref = format_contract_ref(action) if action else ""
        confirmed = bool(ref)
    return VoiceConfirmPayload(
        confirmed=confirmed,
        contract_reference_number=ref,
        notes="regex",
    )
