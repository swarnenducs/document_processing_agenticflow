"""Map JSON onto Word template using the mapper LLM only (no rule fallback)."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from document_processing_agenticflow.models.schemas import (
    ExtractedTemplate,
    FieldMapping,
    MappingResult,
    TableColumnMap,
    TableFillPlan,
)
from document_processing_agenticflow.services.confidence import enrich_mapping_scores


class _LLMFieldMapping(BaseModel):
    """Azure/OpenAI-compatible schema — no Any / untyped fields."""

    json_path: str = Field(description="Dot path into JSON, e.g. customer.name")
    placeholder: str = Field(description="Exact placeholder key from the template")
    value: str = Field(
        default="",
        description="Resolved value as a string (numbers/bools as text)",
    )
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    rationale: str = Field(default="", description="Short reason for the match")


class _LLMTableColumnMap(BaseModel):
    header: str
    json_field: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class _LLMTableFillPlan(BaseModel):
    table_index: int = Field(ge=0)
    array_json_path: str
    columns: list[_LLMTableColumnMap] = Field(default_factory=list)
    rationale: str = Field(default="")


class _LLMMappingPayload(BaseModel):
    """Structured mapper output — all properties have explicit JSON types for Azure."""

    mappings: list[_LLMFieldMapping] = Field(default_factory=list)
    table_fills: list[_LLMTableFillPlan] = Field(default_factory=list)
    unmapped_json_keys: list[str] = Field(default_factory=list)
    unmapped_placeholders: list[str] = Field(default_factory=list)
    notes: str = Field(default="")


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    token = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if token:
                if not isinstance(current, dict) or token not in current:
                    return None
                current = current[token]
                token = ""
            i += 1
            continue
        if ch == "[":
            if token:
                if not isinstance(current, dict) or token not in current:
                    return None
                current = current[token]
                token = ""
            end = path.find("]", i)
            if end == -1:
                return None
            try:
                idx = int(path[i + 1 : end])
            except ValueError:
                return None
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]
            i = end + 1
            continue
        token += ch
        i += 1
    if token:
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _table_summaries(template: ExtractedTemplate) -> list[dict[str, Any]]:
    """Build table header summaries from extracted blocks for the LLM."""
    by_table: dict[int, dict[int, dict[int, str]]] = defaultdict(
        lambda: defaultdict(dict)
    )
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
        body_preview = []
        for r in sorted(rows)[1:3]:
            body_preview.append([rows[r].get(c, "") for c in sorted(rows[0])])
        summaries.append(
            {
                "table_index": t_idx,
                "headers": headers,
                "body_row_count": max(0, len(rows) - 1),
                "body_preview": body_preview,
            }
        )
    return summaries


def _llm_mapping(template: ExtractedTemplate, data: dict[str, Any]) -> MappingResult:
    from document_processing_agenticflow.services.llm_factory import get_mapper_llm, is_mapper_available

    if not is_mapper_available():
        raise RuntimeError(
            "Mapper LLM is required. Check MAPPER_PROVIDER credentials "
            "(for azure_openai: AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT + MAPPER_MODEL)."
        )

    try:
        llm, config = get_mapper_llm(structured_schema=_LLMMappingPayload)
    except (ImportError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"Failed to build mapper LLM: {exc}") from exc

    block_summaries = [
        {
            "block_id": b.block_id,
            "block_type": b.block_type,
            "text": b.text,
            "placeholders": b.placeholder_keys,
            "table_index": b.table_index,
            "row_index": b.row_index,
            "cell_index": b.cell_index,
        }
        for b in template.blocks
        if b.text.strip()
    ]
    tables = _table_summaries(template)

    prompt = f"""You are LLM #1 — a document field mapper.

Analyze the Word TEMPLATE structure and the JSON DATA together.
Decide what values from JSON belong in the document. Do NOT invent business rules
from outside knowledge — only reason over the template text/headers and the JSON.

TEMPLATE PLACEHOLDERS found (forms like {{{{x}}}}, ${{x}}, «x», <X>):
{json.dumps(template.placeholders, indent=2)}

TEMPLATE TABLES (headers + whether body rows exist):
{json.dumps(tables, indent=2)[:6000]}

TEMPLATE CONTENT BLOCKS:
{json.dumps(block_summaries, indent=2)[:10000]}

JSON DATA:
{json.dumps(data, indent=2)[:12000]}

Return structured output:

A) mappings — for each scalar placeholder (DATE, ACCOUNT NAME, invoice_number, etc.):
   - json_path: best path in JSON (dot notation)
   - placeholder: exact placeholder key from the template list
   - value: resolved value from JSON as a STRING (e.g. "24", "Acme", "2026-07-13")
   - confidence: 0-1
   - rationale: short reason
   If JSON has no suitable value, leave that placeholder in unmapped_placeholders.

B) table_fills — when a table should be filled from a JSON array of objects:
   - table_index: which table
   - array_json_path: path to the array (e.g. "products")
   - columns: list of {{header, json_field, confidence}} mapping EACH header to a field
     on objects inside that array (semantic match OK, e.g. "Product Code" → "productCode")
   - rationale

C) unmapped_json_keys / unmapped_placeholders / notes

Important:
- You decide semantic matches by reading headers and JSON keys — no fixed dictionary.
- If the table has only a header row, still create a table_fills plan so rows can be generated.
- Prefer leaving uncertain fields unmapped rather than guessing poorly (confidence < 0.5).
"""

    try:
        result: _LLMMappingPayload = llm.invoke(prompt)  # type: ignore[assignment]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Mapper LLM invoke failed ({config.label}): {exc}") from exc

    mappings: list[FieldMapping] = []
    for item in result.mappings:
        resolved = _resolve_path(data, item.json_path) if item.json_path else None
        if resolved is None and item.value != "":
            # keep LLM-provided string when path does not resolve
            resolved = item.value
        elif resolved is None:
            resolved = item.value if item.value != "" else None
        mappings.append(
            FieldMapping(
                json_path=item.json_path,
                placeholder=item.placeholder,
                value=resolved,
                confidence=item.confidence,
                rationale=item.rationale or None,
            )
        )

    valid_fills: list[TableFillPlan] = []
    for plan in result.table_fills:
        arr = _resolve_path(data, plan.array_json_path)
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and plan.columns:
            valid_fills.append(
                TableFillPlan(
                    table_index=plan.table_index,
                    array_json_path=plan.array_json_path,
                    columns=[
                        TableColumnMap(
                            header=c.header,
                            json_field=c.json_field,
                            confidence=c.confidence,
                        )
                        for c in plan.columns
                    ],
                    rationale=plan.rationale or None,
                )
            )

    if not mappings and not valid_fills:
        raise RuntimeError(
            "Mapper LLM returned no mappings/table_fills. "
            "Check template placeholders and JSON content."
        )

    payload = MappingResult(
        mappings=mappings,
        table_fills=valid_fills,
        unmapped_json_keys=list(result.unmapped_json_keys),
        unmapped_placeholders=list(result.unmapped_placeholders),
        notes=result.notes or f"LLM #1 analyzed template+JSON ({config.label})",
        mapper_source="llm",
        mapper_provider=config.provider,
        mapper_model=config.model,
    )
    enriched = enrich_mapping_scores(payload, len(template.placeholders) or 1)
    if valid_fills and not template.placeholders:
        enriched.coverage_score = 1.0
        enriched.mapping_confidence = max(
            enriched.mapping_confidence,
            sum(c.confidence for p in valid_fills for c in p.columns)
            / max(1, sum(len(p.columns) for p in valid_fills)),
        )
    elif valid_fills:
        enriched.coverage_score = max(enriched.coverage_score, 0.85)
    return enriched


def map_json_to_template(template: ExtractedTemplate, data: dict[str, Any]) -> MappingResult:
    """Step 2: LLM-only mapping of JSON → placeholders / table fills."""
    return _llm_mapping(template, data)
