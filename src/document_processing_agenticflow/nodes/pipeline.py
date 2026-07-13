"""LangGraph nodes for the Word document pipeline (tools-backed services)."""

from __future__ import annotations

import json
from pathlib import Path

from document_processing_agenticflow.models.state import DocumentProcessingState
from document_processing_agenticflow.services.confidence import build_confidence_report
from document_processing_agenticflow.services.document_generator import generate_styled_document
from document_processing_agenticflow.services.document_validator import validate_documents
from document_processing_agenticflow.services.field_mapper import map_json_to_template
from document_processing_agenticflow.services.style_extractor import extract_word_styles


def load_data_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """Load JSON payload that will be mapped onto the Word template."""
    errors = list(state.get("errors") or [])
    data_path = state.get("data_path")
    if not data_path:
        errors.append("data_path is required")
        return {**state, "errors": errors, "status": "failed"}

    path = Path(data_path)
    if not path.exists():
        errors.append(f"Data file not found: {path}")
        return {**state, "errors": errors, "status": "failed"}

    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    if not isinstance(payload, dict):
        errors.append("JSON root must be an object")
        return {**state, "errors": errors, "status": "failed"}

    return {
        **state,
        "json_data": payload,
        "retry_count": state.get("retry_count", 0),
        "max_retries": state.get("max_retries", 1),
        "validation_threshold": state.get("validation_threshold", 0.7),
        "status": "data_loaded",
        "errors": errors,
    }


def extract_styles_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """Step 1 — extract Word XML styles and placeholders from the template."""
    errors = list(state.get("errors") or [])
    if state.get("status") == "failed":
        return state

    template_path = state.get("template_path")
    if not template_path:
        errors.append("template_path is required")
        return {**state, "errors": errors, "status": "failed"}

    try:
        extracted = extract_word_styles(template_path)
    except Exception as exc:  # noqa: BLE001 - surface to graph state
        errors.append(f"Style extraction failed: {exc}")
        return {**state, "errors": errors, "status": "failed"}

    return {
        **state,
        "extracted": extracted,
        "status": "styles_extracted",
        "errors": errors,
    }


def map_fields_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """Step 2 — map JSON data onto template placeholders (LLM #1 required)."""
    errors = list(state.get("errors") or [])
    if state.get("status") == "failed":
        return state

    extracted = state.get("extracted")
    json_data = state.get("json_data")
    if extracted is None or json_data is None:
        errors.append("extracted template and json_data are required before mapping")
        return {**state, "errors": errors, "status": "failed"}

    try:
        mapping = map_json_to_template(extracted, json_data)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Field mapping failed: {exc}")
        return {**state, "errors": errors, "status": "failed"}

    return {
        **state,
        "mapping": mapping,
        "status": "fields_mapped",
        "errors": errors,
    }


def generate_document_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """Step 3 — generate a new .docx with mapped values and preserved styles."""
    errors = list(state.get("errors") or [])
    if state.get("status") == "failed":
        return state

    extracted = state.get("extracted")
    mapping = state.get("mapping")
    output_path = state.get("output_path")
    if extracted is None or mapping is None or not output_path:
        errors.append("extracted, mapping, and output_path are required for generation")
        return {**state, "errors": errors, "status": "failed"}

    try:
        generation = generate_styled_document(
            extracted, mapping, output_path, json_data=state.get("json_data")
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Document generation failed: {exc}")
        return {**state, "errors": errors, "status": "failed"}

    return {
        **state,
        "generation": generation,
        "status": "document_generated",
        "errors": errors,
    }


def validate_document_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """Step 4 — validate template vs generated doc vs JSON (LLM #2 + rules)."""
    errors = list(state.get("errors") or [])
    if state.get("status") == "failed":
        return state

    if state.get("skip_validation"):
        confidence = build_confidence_report(
            state.get("mapping"),
            state.get("generation"),
            None,
        )
        return {
            **state,
            "confidence": confidence,
            "status": "completed",
            "errors": errors,
        }

    extracted = state.get("extracted")
    mapping = state.get("mapping")
    generation = state.get("generation")
    json_data = state.get("json_data")
    if extracted is None or mapping is None or generation is None or json_data is None:
        errors.append("extracted, mapping, generation, and json_data required for validation")
        return {**state, "errors": errors, "status": "failed"}

    try:
        validation = validate_documents(
            extracted,
            generation.output_path,
            json_data,
            mapping,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Validation failed: {exc}")
        return {**state, "errors": errors, "status": "failed"}

    confidence = build_confidence_report(mapping, generation, validation)

    return {
        **state,
        "validation": validation,
        "confidence": confidence,
        "status": "validated",
        "errors": errors,
    }


def finalize_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """Mark pipeline complete and ensure confidence report exists."""
    errors = list(state.get("errors") or [])
    confidence = state.get("confidence")
    if confidence is None:
        confidence = build_confidence_report(
            state.get("mapping"),
            state.get("generation"),
            state.get("validation"),
        )
    return {
        **state,
        "confidence": confidence,
        "status": "completed",
        "errors": errors,
    }
