"""Aggregate confidence scores across mapping, generation, and validation."""

from __future__ import annotations

from document_processing_agenticflow.models.schemas import (
    ConfidenceReport,
    GenerationResult,
    MappingResult,
    ValidationResult,
)
from document_processing_agenticflow.services.scoring import scores_to_percent_dict

DEFAULT_WEIGHTS = {
    "mapping": 0.40,
    "coverage": 0.25,
    "integrity": 0.15,
    "validation": 0.20,
}


def _table_mapping_confidence(mapping: MappingResult | None) -> float:
    if not mapping or not mapping.table_fills:
        return 0.0
    confs = [c.confidence for plan in mapping.table_fills for c in plan.columns]
    if not confs:
        return 0.0
    return sum(confs) / len(confs)


def build_confidence_report(
    mapping: MappingResult | None,
    generation: GenerationResult | None,
    validation: ValidationResult | None,
    weights: dict[str, float] | None = None,
) -> ConfidenceReport:
    """
    Combine component scores into an overall generator confidence (0-1),
    and expose a scores_pct view for UI/API (all values in %).
    """
    w = dict(weights or DEFAULT_WEIGHTS)

    mapping_confidence = mapping.mapping_confidence if mapping else 0.0
    coverage_score = mapping.coverage_score if mapping else 0.0
    table_conf = _table_mapping_confidence(mapping)
    # Blend scalar + table mapping when both exist
    if mapping and mapping.table_fills and mapping.mappings:
        mapping_confidence = (mapping_confidence + table_conf) / 2.0
    elif mapping and mapping.table_fills and not mapping.mappings:
        mapping_confidence = table_conf

    integrity = generation.integrity_score if generation else 0.0
    gen_conf = generation.generation_confidence if generation else 0.0
    validation_score = validation.validation_score if validation else None

    active = {
        "mapping": mapping_confidence,
        "coverage": coverage_score,
        "integrity": integrity,
    }
    active_weights = {
        "mapping": w["mapping"],
        "coverage": w["coverage"],
        "integrity": w["integrity"],
    }

    if validation_score is not None:
        active["validation"] = validation_score
        active_weights["validation"] = w["validation"]
    else:
        total = sum(active_weights.values()) or 1.0
        scale = (sum(w.values()) or 1.0) / total
        active_weights = {k: v * scale for k, v in active_weights.items()}

    weight_sum = sum(active_weights.values()) or 1.0
    overall = sum(active[k] * active_weights[k] for k in active) / weight_sum

    per_field: list[dict] = []
    if mapping:
        for item in mapping.mappings:
            per_field.append(
                {
                    "placeholder": item.placeholder,
                    "json_path": item.json_path,
                    "confidence": item.confidence,
                    "rationale": item.rationale,
                }
            )

    per_table_column: list[dict] = []
    if mapping:
        for plan in mapping.table_fills:
            for col in plan.columns:
                per_table_column.append(
                    {
                        "table_index": plan.table_index,
                        "array_json_path": plan.array_json_path,
                        "header": col.header,
                        "json_field": col.json_field,
                        "confidence": col.confidence,
                        "rationale": plan.rationale,
                    }
                )

    notes_parts: list[str] = []
    if mapping:
        if mapping.mapper_provider and mapping.mapper_model:
            notes_parts.append(f"mapper={mapping.mapper_provider}/{mapping.mapper_model}")
        elif mapping.mapper_source:
            notes_parts.append(f"mapper={mapping.mapper_source}")
    if validation:
        if validation.validator_provider and validation.validator_model:
            notes_parts.append(
                f"validator={validation.validator_provider}/{validation.validator_model}"
            )
        elif validation.validator_source:
            notes_parts.append(f"validator={validation.validator_source}")
    if validation and not validation.passed:
        notes_parts.append("validation_failed")

    mapper_llm = None
    if mapping and mapping.mapper_provider and mapping.mapper_model:
        mapper_llm = f"{mapping.mapper_provider}/{mapping.mapper_model}"
    elif mapping and mapping.mapper_source == "rules":
        mapper_llm = "rules"

    validator_llm = None
    if validation and validation.validator_provider and validation.validator_model:
        validator_llm = f"{validation.validator_provider}/{validation.validator_model}"
    elif validation and validation.validator_source == "rules":
        validator_llm = "rules"

    scores_pct = scores_to_percent_dict(
        overall=overall,
        placeholder_mapping=mapping.mapping_confidence if mapping else 0.0,
        placeholder_coverage=coverage_score,
        table_mapping=table_conf,
        generation_integrity=integrity,
        generation_confidence=gen_conf,
        validation=validation_score if validation_score is not None else 0.0,
        per_placeholder=per_field,
        per_table_column=per_table_column,
    )

    return ConfidenceReport(
        overall_confidence=round(overall, 4),
        mapping_confidence=round(mapping_confidence, 4),
        coverage_score=round(coverage_score, 4),
        table_mapping_confidence=round(table_conf, 4),
        generation_integrity=round(integrity, 4),
        generation_confidence=round(gen_conf, 4),
        validation_score=round(validation_score if validation_score is not None else 0.0, 4),
        validation_passed=validation.passed if validation else None,
        per_field=per_field,
        per_table_column=per_table_column,
        scores_pct=scores_pct,
        weights=active_weights,
        mapper_llm=mapper_llm,
        validator_llm=validator_llm,
        notes="; ".join(notes_parts) if notes_parts else None,
    )


def enrich_mapping_scores(mapping: MappingResult, placeholder_count: int) -> MappingResult:
    """Fill mapping_confidence and coverage_score on a MappingResult."""
    if mapping.mappings:
        mapping.mapping_confidence = sum(m.confidence for m in mapping.mappings) / len(
            mapping.mappings
        )
    elif mapping.table_fills:
        confs = [c.confidence for p in mapping.table_fills for c in p.columns]
        mapping.mapping_confidence = (sum(confs) / len(confs)) if confs else 0.0
    else:
        mapping.mapping_confidence = 0.0

    if placeholder_count > 0:
        mapped = placeholder_count - len(mapping.unmapped_placeholders)
        mapping.coverage_score = mapped / placeholder_count
    elif mapping.table_fills:
        mapping.coverage_score = 1.0
    else:
        mapping.coverage_score = 1.0 if mapping.mappings else 0.0

    mapping.mapping_confidence = round(min(max(mapping.mapping_confidence, 0.0), 1.0), 4)
    mapping.coverage_score = round(min(max(mapping.coverage_score, 0.0), 1.0), 4)
    return mapping
