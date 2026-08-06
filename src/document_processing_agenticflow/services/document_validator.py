"""Validate generated Word docs against template + JSON using the validator LLM only."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel, Field

from document_processing_agenticflow.models.schemas import (
    ExtractedTemplate,
    MappingResult,
    ValidationIssue,
    ValidationResult,
)
from document_processing_agenticflow.services.placeholders import PLACEHOLDER_REGEXES as LEFTOVER_PATTERNS

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _docx_plain_text(path: str | Path) -> str:
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(document_xml)
    parts: list[str] = []
    for node in root.iter():
        if node.tag == _qn("t") and node.text:
            parts.append(node.text)
        elif node.tag == _qn("tab"):
            parts.append("\t")
        elif node.tag == _qn("br"):
            parts.append("\n")
    return "".join(parts)


def _find_leftovers(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in LEFTOVER_PATTERNS:
        for match in pattern.finditer(text):
            key = match.group(1)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found


def _key_value_snippets(generated_text: str, mapping: MappingResult, *, limit: int = 4000) -> str:
    """Pull short windows around mapped values so truncation does not hide fills."""
    snippets: list[str] = []
    seen: set[str] = set()
    for item in mapping.mappings:
        value = "" if item.value is None else str(item.value).strip()
        if not value or value in seen:
            continue
        idx = generated_text.find(value)
        if idx < 0:
            snippets.append(f"[MISSING mapped value for {item.placeholder!r}: {value!r}]")
            seen.add(value)
            continue
        start = max(0, idx - 80)
        end = min(len(generated_text), idx + len(value) + 120)
        window = generated_text[start:end].replace("\n", " ")
        snippets.append(f"- {item.placeholder}={value!r}: …{window}…")
        seen.add(value)
        if sum(len(s) for s in snippets) >= limit:
            break
    # Always include known contract sections when present
    for marker in ("SOLE COMMITMENT", "ADMINISTRATIVE FEE", "Committed Level", "EXHIBIT A"):
        idx = generated_text.find(marker)
        if idx < 0:
            continue
        window = generated_text[idx : idx + 280].replace("\n", " ")
        snippets.append(f"- section {marker}: …{window}…")
    return "\n".join(snippets)[:limit] if snippets else "(no snippets)"


class _LLMValidationIssue(BaseModel):
    severity: str = Field(default="medium", description="high | medium | low")
    field: str = Field(default="", description="Placeholder or field name if known")
    message: str = Field(description="What is wrong")
    expected: str = Field(default="", description="Expected value or state")
    actual: str = Field(default="", description="Actual value or state")


class _LLMValidationPayload(BaseModel):
    passed: bool = False
    validation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[_LLMValidationIssue] = Field(default_factory=list)
    summary: str = Field(default="")


def _llm_validation(
    template: ExtractedTemplate,
    generated_path: str | Path,
    json_data: dict[str, Any],
    mapping: MappingResult,
) -> ValidationResult:
    from document_processing_agenticflow.services.llm_factory import (
        get_validator_llm,
        is_validator_available,
    )

    if not is_validator_available():
        raise RuntimeError(
            "Validator LLM is required. Check VALIDATOR_PROVIDER credentials "
            "(e.g. GROQ_API_KEY or Azure OpenAI settings)."
        )

    from document_processing_agenticflow.services.prompts import build_validator_chain

    try:
        llm, config = get_validator_llm(structured_schema=_LLMValidationPayload)
    except (ImportError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"Failed to build validator LLM: {exc}") from exc

    template_text = "\n".join(b.text for b in template.blocks if b.text.strip())
    generated_text = _docx_plain_text(generated_path)
    leftovers = _find_leftovers(generated_text)
    mapping_summary = [
        {
            "placeholder": m.placeholder,
            "json_path": m.json_path,
            "value": m.value,
            "confidence": m.confidence,
        }
        for m in mapping.mappings
    ]

    chain = build_validator_chain(llm)
    try:
        result: _LLMValidationPayload = chain.invoke(
            {
                "template_text": template_text[:8000],
                "generated_text": generated_text[:8000],
                "key_snippets": _key_value_snippets(generated_text, mapping),
                "data_json": json.dumps(json_data, indent=2)[:8000],
                "mappings_json": json.dumps(mapping_summary, indent=2)[:8000],
                "unmapped_placeholders_json": json.dumps(mapping.unmapped_placeholders),
                "leftovers_json": json.dumps(leftovers),
            }
        )  # type: ignore[assignment]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Validator LLM invoke failed ({config.label}): {exc}") from exc

    issues = [
        ValidationIssue(
            severity=i.severity if i.severity in {"high", "medium", "low"} else "medium",  # type: ignore[arg-type]
            field=i.field or None,
            message=i.message,
            expected=i.expected or None,
            actual=i.actual or None,
        )
        for i in result.issues
    ]

    return ValidationResult(
        passed=result.passed,
        validation_score=round(min(max(result.validation_score, 0.0), 1.0), 4),
        issues=issues,
        summary=result.summary or f"Produced by LLM #2 validator ({config.label})",
        validator_source="llm",
        validator_provider=config.provider,
        validator_model=config.model,
    )


def validate_documents(
    template: ExtractedTemplate,
    generated_path: str | Path,
    json_data: dict[str, Any],
    mapping: MappingResult,
) -> ValidationResult:
    """Step 4: LLM-only validation of template vs generated document vs JSON."""
    return _llm_validation(template, generated_path, json_data, mapping)
