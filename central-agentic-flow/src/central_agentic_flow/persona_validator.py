"""LLM Persona Prompt Validator — runs before the assistant executes."""

from __future__ import annotations

import json
import re
from typing import Any

from central_agentic_flow.prompt_catalog import load_validator_prompt

_CLASSIFICATIONS = {
    "IN_SCOPE",
    "PARTIALLY_IN_SCOPE",
    "OUT_OF_SCOPE",
    "PROHIBITED",
    "INSUFFICIENT_INFORMATION",
}

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def load_validator_instructions() -> str:
    return load_validator_prompt().body


def format_validator_user_message(
    *,
    persona: str,
    persona_definition: str,
    user_prompt: str,
    available_tools: str,
) -> str:
    return (
        f"Persona name: {persona}\n\n"
        f"Persona Definition\n{persona_definition.strip()}\n\n"
        f"User Prompt\n{user_prompt.strip()}\n\n"
        f"Available tools\n{available_tools.strip() or '(none provided)'}\n"
    )


def parse_validator_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Validator returned an empty response")
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Validator response was not JSON")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Validator JSON must be an object")
    classification = str(payload.get("classification") or "").strip().upper()
    if classification not in _CLASSIFICATIONS:
        raise ValueError(f"Unknown classification {classification!r}")
    payload["classification"] = classification
    payload["valid"] = bool(payload.get("valid"))
    if classification in {"OUT_OF_SCOPE", "PROHIBITED"}:
        payload["valid"] = False
    action = str(payload.get("recommended_action") or "").strip().upper()
    if not action:
        action = _default_action(classification)
    payload["recommended_action"] = action
    payload.setdefault("matched_scope", [])
    payload.setdefault("violations", [])
    payload.setdefault("missing_information", [])
    payload.setdefault("required_tools", [])
    payload.setdefault("reason", "")
    payload.setdefault("persona", "")
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1.0:
        confidence = confidence / 100.0
    payload["confidence"] = max(0.0, min(1.0, confidence))
    return payload


def _default_action(classification: str) -> str:
    return {
        "IN_SCOPE": "EXECUTE",
        "PARTIALLY_IN_SCOPE": "PARTIAL",
        "OUT_OF_SCOPE": "REFUSE",
        "PROHIBITED": "REFUSE",
        "INSUFFICIENT_INFORMATION": "CLARIFY",
    }.get(classification, "REFUSE")


def configured_min_confidence() -> float:
    """Minimum validator confidence from settings / env (default 0.95)."""
    from central_agentic_flow.core.settings import get_settings

    return get_settings().maf_persona_validator_min_confidence


def apply_confidence_gate(payload: dict[str, Any]) -> dict[str, Any]:
    threshold = configured_min_confidence()
    confidence = float(payload.get("confidence") or 0.0)
    payload["min_confidence"] = threshold
    if confidence < threshold:
        payload["valid"] = False
        payload["recommended_action"] = "REFUSE"
        note = (
            f"confidence {confidence:.2f} is below configured minimum {threshold:.2f}"
        )
        violations = list(payload.get("violations") or [])
        if note not in violations:
            violations.append(note)
        payload["violations"] = violations
        payload["reason"] = (
            f"{payload.get('reason') or 'Rejected.'} ({note})."
        ).strip()
    return payload


def should_execute(payload: dict[str, Any]) -> bool:
    apply_confidence_gate(payload)
    if float(payload.get("confidence") or 0.0) < float(payload.get("min_confidence") or 0.95):
        return False
    classification = str(payload.get("classification") or "").upper()
    action = str(payload.get("recommended_action") or "").upper()
    if classification in {"PROHIBITED", "OUT_OF_SCOPE"}:
        return False
    if classification == "INSUFFICIENT_INFORMATION":
        return False
    if action == "EXECUTE" and payload.get("valid") is True:
        return True
    if classification == "IN_SCOPE" and payload.get("valid") is True:
        return True
    return False


def describe_available_tools(registry: list[Any]) -> str:
    lines = [
        "Tools are shared. They are not specific to any persona.",
        "Document generation and voice contracts are API jobs, not chat tools.",
        "Never assume a tool exists if it is not listed below.",
    ]
    if not registry:
        lines.append("No chat MCP tools are configured for this turn.")
        return "\n".join(lines)
    for spec in registry:
        name = getattr(spec, "name", None) or getattr(spec, "mcp_key", "mcp")
        prefix = getattr(spec, "prefix", "")
        desc = (getattr(spec, "description", None) or "").strip()
        tools = getattr(spec, "tools", ()) or ()
        tool_names = ", ".join(getattr(rule, "name", str(rule)) for rule in tools) or "(see MCP)"
        lines.append(f"- {name} (prefix={prefix}): {desc or 'MCP'} tools={tool_names}")
    return "\n".join(lines)


async def validate_user_prompt(
    *,
    client: Any,
    persona_definition: str,
    user_prompt: str,
    available_tools: str,
) -> dict[str, Any]:
    """Run the single validator LLM prompt. Does not execute the user prompt."""
    from agent_framework import Agent
    from central_agentic_flow.orchestrator import maf_default_chat_options

    definition = (persona_definition or "").strip()
    if not definition:
        raise ValueError("Provide Persona")
    validator = load_validator_prompt()
    system = validator.body
    human = format_validator_user_message(
        persona=definition.splitlines()[0][:80],
        persona_definition=definition,
        user_prompt=user_prompt,
        available_tools=available_tools,
    )
    async with Agent(
        client=client,
        name="PersonaPromptValidator",
        instructions=system,
        tools=[],
        default_options=maf_default_chat_options(),
    ) as agent:
        response = await agent.run(human)
    raw = getattr(response, "text", None) or str(response)
    payload = parse_validator_json(raw)
    if not payload.get("persona"):
        payload["persona"] = definition.splitlines()[0][:80]
    payload["prompt_version"] = validator.version
    payload["prompt_name"] = validator.name
    return payload
