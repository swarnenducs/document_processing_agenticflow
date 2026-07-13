"""LangGraph workflow: extract → map → generate → validate (+ optional retry)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from document_processing_agenticflow.models.state import DocumentProcessingState
from document_processing_agenticflow.nodes.pipeline import (
    extract_styles_node,
    finalize_node,
    generate_document_node,
    load_data_node,
    map_fields_node,
    validate_document_node,
)


def _should_continue(state: DocumentProcessingState) -> str:
    return "stop" if state.get("status") == "failed" else "continue"


def _after_validation(state: DocumentProcessingState) -> str:
    """Retry map→generate once if validation fails below threshold."""
    if state.get("status") == "failed":
        return "stop"
    if state.get("skip_validation"):
        return "finalize"
    if state.get("status") == "completed":
        return "finalize"

    validation = state.get("validation")
    threshold = state.get("validation_threshold", 0.7)
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)

    if validation is None:
        return "finalize"

    needs_retry = (not validation.passed) or (validation.validation_score < threshold)
    if needs_retry and retry_count < max_retries:
        return "retry"
    return "finalize"


def _bump_retry(state: DocumentProcessingState) -> DocumentProcessingState:
    """Increment retry counter before re-mapping."""
    return {
        **state,
        "retry_count": int(state.get("retry_count") or 0) + 1,
        "status": "retrying",
    }


def build_graph():
    """Compile the document processing LangGraph (pipeline mode)."""
    graph = StateGraph(DocumentProcessingState)

    graph.add_node("load_data", load_data_node)
    graph.add_node("extract_styles", extract_styles_node)
    graph.add_node("map_fields", map_fields_node)
    graph.add_node("generate_document", generate_document_node)
    graph.add_node("validate_document", validate_document_node)
    graph.add_node("bump_retry", _bump_retry)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "load_data")
    graph.add_conditional_edges(
        "load_data",
        _should_continue,
        {"continue": "extract_styles", "stop": END},
    )
    graph.add_conditional_edges(
        "extract_styles",
        _should_continue,
        {"continue": "map_fields", "stop": END},
    )
    graph.add_conditional_edges(
        "map_fields",
        _should_continue,
        {"continue": "generate_document", "stop": END},
    )
    graph.add_conditional_edges(
        "generate_document",
        _should_continue,
        {"continue": "validate_document", "stop": END},
    )
    graph.add_conditional_edges(
        "validate_document",
        _after_validation,
        {
            "retry": "bump_retry",
            "finalize": "finalize",
            "stop": END,
        },
    )
    graph.add_edge("bump_retry", "map_fields")
    graph.add_edge("finalize", END)

    return graph.compile()


# Module-level compiled graph for LangGraph Studio / `langgraph dev`
app = build_graph()
