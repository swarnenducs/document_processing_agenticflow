# LangGraph basics — interview prep

Same depth as LangChain notes: flows, code, memory, and how *this* repo uses graphs.

## Study order

| # | File |
|---|---|
| 1 | [01-core-concepts.md](01-core-concepts.md) — state, nodes, edges, compile |
| 2 | [02-document-graph-code.md](02-document-graph-code.md) — document pipeline + retry |
| 3 | [03-voice-graph-hitl-memory.md](03-voice-graph-hitl-memory.md) — **HITL + SQL checkpointer** |
| 4 | [04-memory-management.md](04-memory-management.md) — memory types & when to use |
| 5 | [05-interview-qa.md](05-interview-qa.md) |

## One-liners

| Term | Meaning |
|---|---|
| **State** | Typed bag every node reads/writes |
| **Node** | `state → partial update` |
| **Conditional edge** | Route by a function over state |
| **Checkpointer** | Persists graph state between turns (SQLAlchemy on SQLite / Azure SQL) |
| **interrupt()** | Pause for human input; resume with `Command` + same `thread_id` |

## This repo

| Graph | Memory? |
|---|---|
| Document (`document-processing-mcp`) | **No** checkpointer — one-shot job |
| Voice (`voice_enable_mcp`) | **Yes** — SQLAlchemy checkpointer + `thread_id` for HITL |
