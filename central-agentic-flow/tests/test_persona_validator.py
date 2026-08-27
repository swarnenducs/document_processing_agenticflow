"""Parse Persona Prompt Validator JSON (no live LLM)."""

from __future__ import annotations

import pytest

from central_agentic_flow.persona_validator import (
    format_validator_user_message,
    load_validator_instructions,
    parse_validator_json,
    should_execute,
)


@pytest.fixture(autouse=True)
def _default_min_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAF_PERSONA_VALIDATOR_MIN_CONFIDENCE", "0.95")


def test_validator_prompt_file_is_external() -> None:
    text = load_validator_instructions()
    assert "Persona Prompt Validator" in text
    assert "IN_SCOPE" in text
    assert "recommended_action" in text


def test_parse_validator_json_from_fenced_block() -> None:
    raw = """Here is the result:
```json
{
  "valid": true,
  "classification": "IN_SCOPE",
  "confidence": 0.95,
  "persona": "sales",
  "reason": "Sales expiration question",
  "matched_scope": ["expirations"],
  "violations": [],
  "missing_information": [],
  "required_tools": [],
  "recommended_action": "EXECUTE"
}
```
"""
    payload = parse_validator_json(raw)
    assert payload["classification"] == "IN_SCOPE"
    assert should_execute(payload) is True


def test_out_of_scope_is_not_executed() -> None:
    payload = parse_validator_json(
        """
        {
          "valid": true,
          "classification": "OUT_OF_SCOPE",
          "confidence": 0.9,
          "persona": "sales",
          "reason": "Legal review is not sales",
          "recommended_action": "EXECUTE"
        }
        """
    )
    assert payload["valid"] is False
    assert payload["recommended_action"] == "EXECUTE"
    assert should_execute(payload) is False


def test_prohibited_is_not_executed() -> None:
    payload = parse_validator_json(
        '{"valid": false, "classification": "PROHIBITED", "reason": "generate docx"}'
    )
    assert should_execute(payload) is False
    assert payload["recommended_action"] == "REFUSE"


def test_insufficient_information_is_not_executed() -> None:
    payload = parse_validator_json(
        '{"valid": true, "classification": "INSUFFICIENT_INFORMATION", "reason": "no dates"}'
    )
    assert payload["recommended_action"] == "CLARIFY"
    assert should_execute(payload) is False


def test_unknown_classification_raises() -> None:
    with pytest.raises(ValueError):
        parse_validator_json('{"classification": "MAYBE"}')


def test_format_validator_user_message_has_sections() -> None:
    text = format_validator_user_message(
        persona="sales",
        persona_definition="You are sales.",
        user_prompt="how many contracts expire next quarter",
        available_tools="- business MCP",
    )
    assert "Persona Definition" in text
    assert "User Prompt" in text
    assert "Available tools" in text
    assert "You are sales." in text


def test_confidence_below_95_is_not_executed() -> None:
    payload = parse_validator_json(
        """
        {
          "valid": true,
          "classification": "IN_SCOPE",
          "confidence": 0.94,
          "recommended_action": "EXECUTE"
        }
        """
    )
    assert should_execute(payload) is False
    assert payload["min_confidence"] == 0.95
    assert payload["recommended_action"] == "REFUSE"
    assert any("below configured minimum" in v for v in payload["violations"])


def test_confidence_at_95_is_allowed() -> None:
    payload = parse_validator_json(
        """
        {
          "valid": true,
          "classification": "IN_SCOPE",
          "confidence": 0.95,
          "recommended_action": "EXECUTE"
        }
        """
    )
    assert should_execute(payload) is True
    assert payload["min_confidence"] == 0.95


def test_percent_confidence_from_validator_is_normalized() -> None:
    payload = parse_validator_json(
        '{"valid": true, "classification": "IN_SCOPE", "confidence": 96, "recommended_action": "EXECUTE"}'
    )
    assert payload["confidence"] == pytest.approx(0.96)
    assert should_execute(payload) is True


def test_min_confidence_from_env_as_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAF_PERSONA_VALIDATOR_MIN_CONFIDENCE", "90")
    payload = parse_validator_json(
        '{"valid": true, "classification": "IN_SCOPE", "confidence": 0.91, "recommended_action": "EXECUTE"}'
    )
    assert should_execute(payload) is True
    payload_low = parse_validator_json(
        '{"valid": true, "classification": "IN_SCOPE", "confidence": 0.89, "recommended_action": "EXECUTE"}'
    )
    assert should_execute(payload_low) is False
    assert payload_low["min_confidence"] == pytest.approx(0.90)
