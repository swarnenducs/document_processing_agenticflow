# 02 — Document graph (this repo)

**Package:** `document-processing-mcp`  
**No checkpointer** — each job is a single `invoke` / `stream`.

## Flow

```text
START
  → load_data
  → extract_styles
  → map_fields          # Mapper LLM
  → generate            # OOXML / python-docx
  → validate            # Validator LLM
       ├─ pass  → finalize → END
       ├─ fail hard → END
       └─ low score & retries left → bump_retry → map_fields
```

## Sketch of graph wiring

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(DocumentProcessingState)
graph.add_node("load_data", load_data_node)
graph.add_node("extract_styles", extract_styles_node)
graph.add_node("map_fields", map_fields_node)
graph.add_node("generate", generate_node)
graph.add_node("validate", validate_node)
graph.add_node("bump_retry", bump_retry_node)
graph.add_node("finalize", finalize_node)

graph.add_edge(START, "load_data")
graph.add_edge("load_data", "extract_styles")
# ... linear edges ...
graph.add_conditional_edges("validate", after_validation, {
    "finalize": "finalize",
    "retry": "bump_retry",
    "fail": END,
})
graph.add_edge("bump_retry", "map_fields")
graph.add_edge("finalize", END)

app = graph.compile()  # no MemorySaver
```

## Why no memory here?

Document generation is a **batch job**: upload → run → download.  
No multi-turn conversation. Failures retry **inside one run** via state `retry_count`, not across HTTP requests.

**Interview line:** “In-run retry uses graph state; cross-request memory needs a checkpointer + thread_id — we use that on voice, not document.”

## Streaming for UX

API job runner can `stream` node updates and publish WebSocket stages (`styles_extracted`, `fields_mapped`, …) without needing a checkpointer.

Point to: `document-processing-mcp/.../graph.py`, `nodes/pipeline.py`

Next: [03-voice-graph-hitl-memory.md](03-voice-graph-hitl-memory.md)
