# 03 — Voice graph, HITL, and memory (this repo)

## Direct answer: does voice use memory?

**Yes.** Voice uses LangGraph **checkpoint memory**:

- `MemorySaver` (in-process checkpointer)
- `thread_id` in `config["configurable"]`
- `interrupt()` in `await_confirmation` for human-in-the-loop
- Resume with same `thread_id` via `Command(resume=...)`

It is **not** full chat-history RAG memory — it is **workflow state persistence** so HITL can pause and continue.

---

## Code (from `voice_enable_mcp/.../graph.py`)

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

_CHECKPOINTER = MemorySaver()

def build_voice_contract_graph(*, checkpointer=None):
    graph = StateGraph(VoiceContractState)
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("fetch_legal_entity", fetch_legal_entity_node)
    graph.add_node("fetch_pricelist", fetch_pricelist_node)
    graph.add_node("await_confirmation", await_confirmation_node)  # interrupt()
    graph.add_node("generate_contract", generate_contract_node)
    # ... edges ...
    return graph.compile(checkpointer=checkpointer or _CHECKPOINTER)
```

### Start turn

```python
tid = thread_id or str(uuid.uuid4())
config = {"configurable": {"thread_id": tid}}
out = graph.invoke({...}, config=config)
# if interrupt → status needs_confirmation, return tid to client
```

### Confirm turn (resume)

```python
config = {"configurable": {"thread_id": thread_id}}
out = graph.invoke(Command(resume=user_payload), config=config)
```

### Interrupt node (concept)

```python
from langgraph.types import interrupt

def await_confirmation_node(state):
    decision = interrupt({
        "message": "Confirm legal entity and contract reference",
        "candidates": state.get("candidates"),
        "thread_id": state.get("thread_id"),
    })
    # after resume, `decision` is the user's confirmation payload
    return {**state, "confirmation": decision, "status": "confirmed"}
```

---

## Sequence

```text
User: "create contract AVC CR 1001"
  → parse → lookup entity/pricelist
  → interrupt (pause)  ★ state saved in MemorySaver under thread_id
  → API returns needs_confirmation + thread_id

User: "yes" / confirm
  → resume same thread_id
  → generate_contract → save → END
```

---

## Limits of `MemorySaver` (say this in interviews)

| Pros | Cons |
|---|---|
| Zero infra, great for local/HITL demo | **Lost on process restart** |
| Fast | Not shared across multiple MCP replicas |

**Production:** swap to `PostgresSaver` / Redis checkpointer so any replica can resume the thread.

Also: completed contracts are saved to **SQLite** (durable business data) — that’s separate from graph checkpoint memory.

Next: [04-memory-management.md](04-memory-management.md)
