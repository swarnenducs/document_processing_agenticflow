"""LLM critic for deterministic Word XML extraction (confidence on extracted structure)."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from document_processing_agenticflow.models.schemas import (
    ExtractionValidationResult,
    ExtractedTemplate,
    ValidationIssue,
)


class _LLMExtractionIssue(BaseModel):
    severity: str = Field(default="medium", description="high | medium | low")
    field: str = Field(default="", description="Placeholder or block id if known")
    message: str = Field(description="What is wrong with the extraction")
    expected: str = Field(default="")
    actual: str = Field(default="")


class _LLMExtractionPayload(BaseModel):
    passed: bool = False
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    placeholder_detection_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    structure_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[_LLMExtractionIssue] = Field(default_factory=list)
    summary: str = Field(default="")
    missed_placeholder_suspects: list[str] = Field(default_factory=list)


def _table_summaries(template: ExtractedTemplate) -> list[dict[str, Any]]:
    by_table: dict[int, dict[int, dict[int, str]]] = defaultdict(lambda: defaultdict(dict))
    for b in template.blocks:
        if b.block_type != "table_cell" or b.table_index is None:
            continue
        if b.row_index is None or b.cell_index is None:
            continue
        by_table[b.table_index][b.row_index][b.cell_index] = b.text.strip()

    summaries: list[dict[str, Any]] = []
    for t_idx in sorted(by_table):
        rows = by_table[t_idx]
        if 0 not in rows:
            continue
        headers = [rows[0][c] for c in sorted(rows[0])]
        summaries.append(
            {
                "table_index": t_idx,
                "headers": headers,
                "body_row_count": max(0, len(rows) - 1),
            }
        )
    return summaries


def validate_extraction(template: ExtractedTemplate) -> ExtractionValidationResult:
    """
    LLM critic of XML extraction quality.
    Soft-skips (returns passed=True, confidence=None-ish) only via caller when unavailable;
    this function requires a live validator LLM.
    """
    from document_processing_agenticflow.services.llm_factory import (
        get_validator_llm,
        is_validator_available,
    )
    from document_processing_agenticflow.services.prompts.extraction_validator_prompt import (
        build_extraction_validator_chain,
    )

    if not is_validator_available():
        raise RuntimeError(
            "Extraction validator LLM is required. Check VALIDATOR_PROVIDER credentials."
        )

    llm, config = get_validator_llm(structured_schema=_LLMExtractionPayload)
    block_summaries = [
        {
            "block_id": b.block_id,
            "block_type": b.block_type,
            "text": b.text[:400],
            "placeholder_keys": b.placeholder_keys,
            "table_index": b.table_index,
        }
        for b in template.blocks
        if (b.text or "").strip()
    ]
    chain = build_extraction_validator_chain(llm)
    result: _LLMExtractionPayload = chain.invoke(
        {
            "template_path": template.template_path,
            "placeholders_json": json.dumps(template.placeholders, indent=2),
            "blocks_json": json.dumps(block_summaries, indent=2)[:12000],
            "tables_json": json.dumps(_table_summaries(template), indent=2)[:4000],
        }
    )  # type: ignore[assignment]

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

    return ExtractionValidationResult(
        passed=bool(result.passed),
        extraction_confidence=round(min(max(result.extraction_confidence, 0.0), 1.0), 4),
        placeholder_detection_confidence=round(
            min(max(result.placeholder_detection_confidence, 0.0), 1.0), 4
        ),
        structure_confidence=round(min(max(result.structure_confidence, 0.0), 1.0), 4),
        issues=issues,
        summary=result.summary or f"Extraction critic ({config.label})",
        detected_placeholders=list(template.placeholders),
        missed_placeholder_suspects=list(result.missed_placeholder_suspects),
        validator_source="llm",
        validator_provider=config.provider,
        validator_model=config.model,
    )
