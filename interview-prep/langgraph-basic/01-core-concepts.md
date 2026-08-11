# 01 — LangGraph core concepts

## Why LangGraph?

When control flow matters (retry, branch, human pause), a **graph** beats a giant `for`/`if` around LLM calls.

```text
LLM apps need:
  - deterministic steps (extract → map → generate)
  - conditional routing (retry if score low)
  - pause/resume (human confirms)
→ LangGraph
```

---

## Minimal graph (code)

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    text: str
    summary: str
    status: str

def summarize(state: State) -> dict:
    # pretend LLM call
    return {"summary": state["text"][:50], "status": "ok"}

def too_short(state: State) -> str:
    return "retry" if len(state.get("summary", "")) < 10 else "done"

g = StateGraph(State)
g.add_node("summarize", summarize)
g.add_edge(START, "summarize")
g.add_conditional_edges("summarize", too_short, {"retry": "summarize", "done": END})
app = g.compile()

print(app.invoke({"text": "Hello world from LangGraph", "summary": "", "status": ""}))
```

---

## Building blocks

### State

```python
class DocumentProcessingState(TypedDict, total=False):
    template_path: str
    data_path: str
    mapping: dict
    errors: list[str]
    status: str
    retry_count: int
    max_retries: int
```

**Interview:** State is the contract between nodes. Side effects (disk, LLM) live in services; nodes orchestrate.

### Nodes

```python
def map_fields_node(state: DocumentProcessingState) -> DocumentProcessingState:
    mapping = map_json_to_template(...)  # service call
    return {**state, "mapping": mapping, "status": "mapped"}
```

### Edges

```python
graph.add_edge("extract_styles", "map_fields")  # always next

graph.add_conditional_edges(
    "validate",
    route_after_validation,  # returns "finalize" | "retry" | "fail"
    {"finalize": "finalize", "retry": "bump_retry", "fail": END},
)
```

### Compile + run

```python
app = graph.compile()                    # no memory
app = graph.compile(checkpointer=saver) # with memory / HITL

app.invoke(initial_state)
app.invoke(initial_state, config={"configurable": {"thread_id": "abc"}})

for event in app.stream(initial_state):
    ...
```

---

## Document vs voice (whiteboard)

```text
DOCUMENT (one-shot job)
START → load → extract → map → generate → validate
                                    ↓ fail+retries
                              bump_retry → map

VOICE (multi-turn HITL)
START → parse → fetch entity → fetch pricelist
      → await_confirmation [INTERRUPT]
      → generate_contract → END
```

Next: [02-document-graph-code.md](02-document-graph-code.md)
