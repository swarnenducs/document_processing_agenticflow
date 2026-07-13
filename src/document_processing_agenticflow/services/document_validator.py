"""Validate generated Word docs against the template and source JSON (LLM #2 + rules)."""

from __future__ import annotations

import json
import re
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
NS = {"w": W_NS}


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


def _rule_based_validation(
    template: ExtractedTemplate,
    generated_path: str | Path,
    json_data: dict[str, Any],
    mapping: MappingResult,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    generated_text = _docx_plain_text(generated_path)

    leftovers = _find_leftovers(generated_text)
    unmapped = set(mapping.unmapped_placeholders)
    for key in leftovers:
        # Unmapped leftovers are expected (missing JSON fields); mapped leftovers are real bugs
        severity = "medium" if key in unmapped else "high"
        issues.append(
            ValidationIssue(
                severity=severity,  # type: ignore[arg-type]
                field=key,
                message=f"Leftover placeholder still present: <{key}> (or equivalent token)",
                expected="filled value from JSON",
                actual=f"<{key}>",
            )
        )

    missing_values = 0
    checked = 0
    for item in mapping.mappings:
        if item.value is None:
            continue
        value_str = str(item.value)
        if not value_str:
            continue
        checked += 1
        if value_str not in generated_text:
            missing_values += 1
            issues.append(
                ValidationIssue(
                    severity="high",
                    field=item.placeholder,
                    message="Mapped value not found in generated document",
                    expected=value_str,
                    actual=None,
                )
            )

    for placeholder in mapping.unmapped_placeholders:
        issues.append(
            ValidationIssue(
                severity="medium",
                field=placeholder,
                message="Placeholder was never mapped from JSON",
            )
        )

    # Style part presence check (styles.xml should still exist)
    with zipfile.ZipFile(generated_path, "r") as zf:
        if "word/styles.xml" not in zf.namelist():
            issues.append(
                ValidationIssue(
                    severity="high",
                    field=None,
                    message="word/styles.xml missing from generated document",
                )
            )

    high = sum(1 for i in issues if i.severity == "high")
    medium = sum(1 for i in issues if i.severity == "medium")
    # Score: start at 1.0, subtract for issues
    score = 1.0
    score -= 0.15 * high
    score -= 0.05 * medium
    if checked:
        score -= 0.1 * (missing_values / checked)
    score = round(min(max(score, 0.0), 1.0), 4)

    passed = high == 0 and score >= 0.7
    return ValidationResult(
        passed=passed,
        validation_score=score,
        issues=issues,
        summary=(
            f"Rule validator: {len(issues)} issue(s), "
            f"{checked - missing_values}/{checked} mapped values found in output"
            if checked
            else f"Rule validator: {len(issues)} issue(s)"
        ),
        validator_source="rules",
        validator_provider="rules",
        validator_model=None,
    )


class _LLMValidationPayload(BaseModel):
    passed: bool = False
    validation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[ValidationIssue] = Field(default_factory=list)
    summary: str | None = None


def _llm_validation(
    template: ExtractedTemplate,
    generated_path: str | Path,
    json_data: dict[str, Any],
    mapping: MappingResult,
) -> ValidationResult | None:
    from document_processing_agenticflow.services.llm_factory import (
        get_validator_llm,
        is_validator_available,
    )

    if not is_validator_available():
        return None

    try:
        llm, config = get_validator_llm(structured_schema=_LLMValidationPayload)
    except (ImportError, RuntimeError, ValueError):
        return None

    template_text = "\n".join(b.text for b in template.blocks if b.text.strip())
    generated_text = _docx_plain_text(generated_path)
    mapping_summary = [
        {
            "placeholder": m.placeholder,
            "json_path": m.json_path,
            "value": m.value,
            "confidence": m.confidence,
        }
        for m in mapping.mappings
    ]

    prompt = f"""You are a strict document QA critic (LLM #2 — {config.label}). Compare:
1) the Word TEMPLATE text/placeholders
2) the GENERATED document text
3) the source JSON data
4) the field mappings used

Decide if the generated document correctly reflects the JSON while preserving template structure.

TEMPLATE TEXT:
{template_text[:8000]}

GENERATED TEXT:
{generated_text[:8000]}

JSON DATA:
{json.dumps(json_data, indent=2)[:8000]}

MAPPINGS:
{json.dumps(mapping_summary, indent=2)[:8000]}

UNMAPPED PLACEHOLDERS: {json.dumps(mapping.unmapped_placeholders)}

Rules for scoring (validation_score 0-1):
- 1.0 = all mapped values present, no leftover placeholders, structure intact
- Deduct heavily for wrong/missing values or leftover {{{{placeholders}}}}
- Deduct moderately for unmapped placeholders or style/structure concerns
- Set passed=true only if there are no high-severity issues and score >= 0.7
- List concrete issues with severity high|medium|low
"""

    try:
        result: _LLMValidationPayload = llm.invoke(prompt)  # type: ignore[assignment]
    except Exception:
        return None
    source_tag = f"{config.provider}+rules" if config.provider != "rules" else config.provider
    return ValidationResult(
        passed=result.passed,
        validation_score=round(min(max(result.validation_score, 0.0), 1.0), 4),
        issues=result.issues,
        summary=result.summary or f"Produced by LLM #2 validator ({config.label})",
        validator_source=source_tag,
        validator_provider=config.provider,
        validator_model=config.model,
    )


def validate_documents(
    template: ExtractedTemplate,
    generated_path: str | Path,
    json_data: dict[str, Any],
    mapping: MappingResult,
    *,
    prefer_llm: bool = True,
) -> ValidationResult:
    """
    Step 4: Validate template vs generated document vs JSON.
    Uses a separate validator LLM when available; always merges with rule checks.
    """
    rules = _rule_based_validation(template, generated_path, json_data, mapping)

    if not prefer_llm:
        return rules

    llm_result = _llm_validation(template, generated_path, json_data, mapping)
    if llm_result is None:
        return rules

    # Merge: keep LLM score/summary, but always surface rule high-severity leftovers
    merged_issues = list(llm_result.issues)
    existing = {(i.field, i.message) for i in merged_issues}
    for issue in rules.issues:
        key = (issue.field, issue.message)
        if key not in existing and issue.severity == "high":
            merged_issues.append(issue)

    high = any(i.severity == "high" for i in merged_issues)
    # Conservative: take the min of LLM and rule scores when rules found high issues
    score = llm_result.validation_score
    if high:
        score = min(score, rules.validation_score)

    return ValidationResult(
        passed=llm_result.passed and not high and score >= 0.7,
        validation_score=round(score, 4),
        issues=merged_issues,
        summary=llm_result.summary,
        validator_source=f"{llm_result.validator_provider}+rules"
        if llm_result.validator_provider
        else "llm+rules",
        validator_provider=llm_result.validator_provider,
        validator_model=llm_result.validator_model,
    )
