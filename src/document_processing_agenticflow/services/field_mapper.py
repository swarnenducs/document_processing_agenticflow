"""Map JSON onto Word template — LLM analyzes both; rules are exact-match fallback only."""

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
from document_processing_agenticflow.services.placeholders import generic_key_variants


class _LLMMappingPayload(BaseModel):
    mappings: list[FieldMapping] = Field(default_factory=list)
    table_fills: list[TableFillPlan] = Field(default_factory=list)
    unmapped_json_keys: list[str] = Field(default_factory=list)
    unmapped_placeholders: list[str] = Field(default_factory=list)
    notes: str | None = None


def _flatten_json(data: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten_json(value, path))
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            path = f"{prefix}[{idx}]"
            flat.update(_flatten_json(value, path))
    else:
        flat[prefix] = data
    return flat


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


def _rule_based_mapping(template: ExtractedTemplate, data: dict[str, Any]) -> MappingResult:
    """
    Fallback ONLY when LLM is unavailable.
    Exact / generic string-variant matches — no business synonym dictionary.
    """
    flat = _flatten_json(data)
    leaf_index: dict[str, list[str]] = {}
    for path in flat:
        leaf = path.split(".")[-1].split("[")[0]
        leaf_index.setdefault(leaf.lower(), []).append(path)

    mappings: list[FieldMapping] = []
    used_paths: set[str] = set()
    mapped_placeholders: set[str] = set()

    for placeholder in template.placeholders:
        candidates = generic_key_variants(placeholder)
        if "." in placeholder:
            candidates.append(placeholder.split(".")[-1])

        matched_path: str | None = None
        for candidate in candidates:
            if candidate in flat:
                matched_path = candidate
                break
            leaf_hits = leaf_index.get(candidate.lower(), [])
            if len(leaf_hits) == 1:
                matched_path = leaf_hits[0]
                break
            value = _resolve_path(data, candidate)
            if value is not None:
                matched_path = candidate
                break

        if matched_path is None:
            continue

        value = flat.get(matched_path)
        if value is None:
            value = _resolve_path(data, matched_path)

        block_id = next(
            (b.block_id for b in template.blocks if placeholder in b.placeholder_keys),
            None,
        )
        mappings.append(
            FieldMapping(
                json_path=matched_path,
                placeholder=placeholder,
                block_id=block_id,
                value=value,
                confidence=0.7,
                rationale="Exact/generic string match (rule fallback — prefer LLM)",
            )
        )
        used_paths.add(matched_path)
        mapped_placeholders.add(placeholder)

    # Naive table fill: if JSON has exactly one list-of-dicts and a table exists,
    # leave columns empty for LLM; rules only attempt exact header==field name
    table_fills: list[TableFillPlan] = []
    tables = _table_summaries(template)
    list_paths = [
        k
        for k, v in data.items()
        if isinstance(v, list) and v and all(isinstance(i, dict) for i in v)
    ]
    if tables and len(list_paths) == 1:
        array_key = list_paths[0]
        sample = data[array_key][0]
        sample_keys = {str(k).lower(): str(k) for k in sample}
        for tbl in tables:
            cols: list[TableColumnMap] = []
            for header in tbl["headers"]:
                matched = None
                for variant in generic_key_variants(header):
                    if variant in sample:
                        matched = variant
                        break
                    if variant.lower() in sample_keys:
                        matched = sample_keys[variant.lower()]
                        break
                if matched:
                    cols.append(
                        TableColumnMap(header=header, json_field=matched, confidence=0.65)
                    )
            if cols:
                table_fills.append(
                    TableFillPlan(
                        table_index=tbl["table_index"],
                        array_json_path=array_key,
                        columns=cols,
                        rationale="Rule fallback: exact header/field name match only",
                    )
                )

    result = MappingResult(
        mappings=mappings,
        table_fills=table_fills,
        unmapped_json_keys=[p for p in flat if p not in used_paths],
        unmapped_placeholders=[p for p in template.placeholders if p not in mapped_placeholders],
        notes="Rule fallback only (no LLM). Semantic matching requires OPENAI_API_KEY.",
        mapper_source="rules",
        mapper_provider="rules",
        mapper_model=None,
    )
    return enrich_mapping_scores(result, len(template.placeholders) or 1)


def _llm_mapping(template: ExtractedTemplate, data: dict[str, Any]) -> MappingResult | None:
    from document_processing_agenticflow.services.llm_factory import get_mapper_llm, is_mapper_available

    if not is_mapper_available():
        return None

    try:
        llm, config = get_mapper_llm(structured_schema=_LLMMappingPayload)
    except (ImportError, RuntimeError, ValueError):
        return None

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
   - value: resolved value from JSON (string/number)
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
    except Exception:
        return None

    for mapping in result.mappings:
        if mapping.value is None and mapping.json_path:
            mapping.value = _resolve_path(data, mapping.json_path)
        if mapping.confidence is None:
            mapping.confidence = 0.7

    # Validate table fill array paths exist
    valid_fills: list[TableFillPlan] = []
    for plan in result.table_fills:
        arr = _resolve_path(data, plan.array_json_path)
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and plan.columns:
            valid_fills.append(plan)

    payload = MappingResult(
        mappings=result.mappings,
        table_fills=valid_fills,
        unmapped_json_keys=result.unmapped_json_keys,
        unmapped_placeholders=result.unmapped_placeholders,
        notes=result.notes or f"LLM #1 analyzed template+JSON ({config.label})",
        mapper_source="llm",
        mapper_provider=config.provider,
        mapper_model=config.model,
    )
    # Coverage considers placeholders + whether tables were planned
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
    """
    Step 2: LLM analyzes template + JSON to decide placeholder and table mappings.
    Falls back to exact-match rules only when LLM is unavailable.
    """
    llm_result = _llm_mapping(template, data)
    if llm_result is not None and (llm_result.mappings or llm_result.table_fills):
        return llm_result
    return _rule_based_mapping(template, data)
