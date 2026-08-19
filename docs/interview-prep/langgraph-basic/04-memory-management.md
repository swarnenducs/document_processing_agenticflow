# 04 — Memory management (GenAI interviews)

## When do you need memory?

| Need | Example | Memory type |
|---|---|---|
| Multi-turn chat (“what did I just say?”) | Chatbot | Conversation / buffer memory |
| Pause workflow for human | Approve a contract | **Checkpoint / thread state** |
| Long-running agent with facts | “User’s company is Acme” | Long-term / profile store |
| Q&A over documents | Policy bot | **RAG** (not chat memory) |
| One-shot batch job | Fill one DOCX | **None** (pass state in one invoke) |

**Rule of thumb:**  
- Same HTTP request / one graph run → state dict is enough.  
- Across requests / HITL → checkpointer + `thread_id`.  
- Across weeks of user facts → DB / vector store.  
- Private knowledge Q&A → RAG.

---

## Types of memory (name them correctly)

### 1) Short-term conversation memory

Keeps last N messages in the prompt.

```python
# LangChain-style idea
history = InMemoryChatMessageHistory()
# or BufferWindowMemory(k=10) in older APIs
```

**Use when:** chatbot continuity.  
**Risk:** token blow-up → summarize or window.

### 2) Summary memory

Compress old turns into a running summary; keep recent raw messages.

**Use when:** long sessions.

### 3) LangGraph checkpoint memory (workflow memory)

Persists **graph state** (and interrupt) keyed by `thread_id`.

```python
from langgraph.checkpoint.memory import MemorySaver
app = graph.compile(checkpointer=MemorySaver())

app.invoke(state, config={"configurable": {"thread_id": "t-1"}})
# later
app.invoke(Command(resume=...), config={"configurable": {"thread_id": "t-1"}})
```

**Use when:** HITL, multi-step agents, durable workflows.  
**This is what our voice path uses.**

### 4) Long-term / entity memory

Store user preferences, account ids in Postgres/Redis.

**Use when:** personalization across sessions.

### 5) RAG “memory”

Vector index of documents — retrieval, not dialogue.

**Use when:** knowledge grounding (see LangChain RAG notes).

---

## How we implement memory in *this* project

| Component | Memory? | Implementation |
|---|---|---|
| Document LangGraph | No cross-request memory | In-run `retry_count` in state only |
| **Voice LangGraph** | **Yes** | `MemorySaver` + `thread_id` + `interrupt()` |
| Voice completed contracts | Durable business data | SQLite (`JobStore`) |
| MAF `/ask` | **Stateless per call today** | Each ask is a new `agent.run(message)` — no session store yet |
| API jobs | Job rows | SQLite + files |

### Voice (actual)

```python
# voice_enable_mcp/graph.py
_CHECKPOINTER = MemorySaver()
graph.compile(checkpointer=_CHECKPOINTER)
# start/resume with config={"configurable": {"thread_id": tid}}
```

### Document

```python
graph.compile()  # no checkpointer
```

### If we added MAF session memory later

```python
# Conceptual MAF / Agent Framework session
session = AgentSession(...)  # framework-specific
await agent.run(message, session=session)
# or store prior messages yourself and pass conversation history
```

---

## Choosing a checkpointer

| Saver | When |
|---|---|
| `MemorySaver` | Local, single process, demos |
| Sqlite/Postgres checkpointer | Multi-replica, survive restarts |
| Redis | Low-latency shared state |

---

## Interview one-liners

> “Voice needs memory because HITL pauses mid-graph; we use LangGraph `MemorySaver` keyed by `thread_id`. Document jobs don’t — they’re one-shot. MAF asks are currently stateless; we’d add a session if we wanted multi-turn orchestration.”

Next: [05-interview-qa.md](05-interview-qa.md)
