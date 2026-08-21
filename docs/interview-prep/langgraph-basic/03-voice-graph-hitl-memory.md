# 03 — Voice graph, HITL, and memory (this repo)

## Direct answer: does voice use memory?

**Yes.** Voice uses LangGraph **checkpoint memory**:

- SQLAlchemy checkpointer (`SqlAlchemyCheckpointSaver`) on the same SQLite / Azure SQL database as the rest of the voice MCP
- `thread_id` in `config["configurable"]`
- `interrupt()` in `await_confirmation` for human-in-the-loop
- Resume with same `thread_id` via `Command(resume=...)`

It is **not** full chat-history RAG memory — it is **workflow state persistence** so HITL can pause and continue after a restart or on another replica that shares the database.

---

## Code (from `voice_enable_mcp/.../graph.py`)

```python
from langgraph.graph import StateGraph, START, END
from voice_enable_mcp.storage.checkpoint_store import SqlAlchemyCheckpointSaver

def get_checkpointer():
    return SqlAlchemyCheckpointSaver()  # SQLite locally, Azure SQL in cloud

def build_voice_contract_graph(*, checkpointer=None):
    graph = StateGraph(VoiceContractState)
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("fetch_legal_entity", fetch_legal_entity_node)
    graph.add_node("fetch_pricelist", fetch_pricelist_node)
    graph.add_node("await_confirmation", await_confirmation_node)  # interrupt()
    graph.add_node("generate_contract", generate_contract_node)
    # ... edges ...
    return graph.compile(checkpointer=checkpointer or get_checkpointer())
```

Tables: `lg_checkpoints`, `lg_checkpoint_blobs`, `lg_checkpoint_writes`.

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
  -> interrupt (pause); state is saved in SQL under thread_id
  → API returns needs_confirmation + thread_id

User: "yes" / confirm
  → resume same thread_id (even after MCP restart)
  → generate_contract → save → END
```

---

## Why SQLAlchemy instead of Postgres/Redis (say this in interviews)

LangGraph's official durable savers are `PostgresSaver` and `SqliteSaver` (sqlite3, not SQLAlchemy). This repo already standardizes on **SQLite locally + Azure SQL in cloud**, so the default path implements `BaseCheckpointSaver` on SQLAlchemy.

Set `LANGGRAPH_CHECKPOINT_BACKEND=redis` + `REDIS_URL` to swap HITL checkpoints onto Redis (vanilla Redis / Azure Cache; no RediSearch). Completed contracts stay in SQL either way.

| Pros | Still true |
|---|---|
| Same engine as contracts / call logs | No extra datastore |
| Survives process restart | Multi-replica as long as they share the DB |
| Azure SQL works (no official MSSQL saver) | Not LangGraph's Postgres wire format |

Completed contracts in `voice_contracts` are **business data** (always SQL). Checkpoint rows are **workflow snapshots** (SQL by default, Redis when `LANGGRAPH_CHECKPOINT_BACKEND=redis`).

Next: [04-memory-management.md](04-memory-management.md)
