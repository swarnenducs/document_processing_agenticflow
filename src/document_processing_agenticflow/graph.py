"""LangGraph workflow: extract → extraction-validate → map → generate → validate."""

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
    validate_extraction_node,
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
    graph.add_node("validate_extraction", validate_extraction_node)
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
        {"continue": "validate_extraction", "stop": END},
    )
    graph.add_conditional_edges(
        "validate_extraction",
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


def invoke_document_graph(
    state: DocumentProcessingState | dict,
    *,
    config: dict | None = None,
    mapper_model_id: str | None = None,
    validator_model_id: str | None = None,
):
    """
    Run the compiled LangGraph with optional ``init_chat_model`` provider switches.

    Example::

        invoke_document_graph(
            state,
            mapper_model_id="openai:gpt-4o-mini",
            validator_model_id="anthropic:claude-sonnet-4-20250514",
        )

        # or LangGraph-style configurable:
        invoke_document_graph(state, config={"configurable": {
            "mapper_model_id": "groq:openai/gpt-oss-120b",
        }})
    """
    final = None
    for snapshot in stream_document_graph(
        state,
        config=config,
        mapper_model_id=mapper_model_id,
        validator_model_id=validator_model_id,
    ):
        final = snapshot
    return final


def stream_document_graph(
    state: DocumentProcessingState | dict,
    *,
    config: dict | None = None,
    mapper_model_id: str | None = None,
    validator_model_id: str | None = None,
):
    """Yield full graph state after each node (for live progress / WebSockets)."""
    from document_processing_agenticflow.services.llm_factory import (
        bind_model_overrides_from_config,
        reset_role_model_overrides,
        set_role_model_overrides,
    )

    payload = dict(state)
    if mapper_model_id:
        payload["mapper_model_id"] = mapper_model_id
    if validator_model_id:
        payload["validator_model_id"] = validator_model_id

    run_config = dict(config or {})
    configurable = dict(run_config.get("configurable") or {})
    if mapper_model_id:
        configurable["mapper_model_id"] = mapper_model_id
    if validator_model_id:
        configurable["validator_model_id"] = validator_model_id
    if configurable:
        run_config["configurable"] = configurable

    tokens = bind_model_overrides_from_config(run_config)
    if mapper_model_id or validator_model_id:
        reset_role_model_overrides(tokens)
        tokens = set_role_model_overrides(
            mapper_model_id=mapper_model_id or configurable.get("mapper_model_id"),
            validator_model_id=validator_model_id or configurable.get("validator_model_id"),
        )
    try:
        for snapshot in build_graph().stream(
            payload, config=run_config or None, stream_mode="values"
        ):
            yield snapshot
    finally:
        reset_role_model_overrides(tokens)


# Module-level compiled graph for LangGraph Studio / `langgraph dev`
app = build_graph()
