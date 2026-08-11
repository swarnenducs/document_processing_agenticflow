# Use-case: Memory types in LangGraph vs MAF

## Problem
You want multi-turn “conversation memory” and also support **HITL pause/resume** (like voice confirmation). These are different needs, so “memory” should be picked based on *where* the state lives and *how long* it must persist.

This repo has:
- **LangGraph** specialist flows (document generation, voice contract with HITL)
- A **MAF central agent** that orchestrates specialist flows as MCP tool calls

## Part A — LangGraph memory options (what to use + why)

### 1) In-graph state (the `State` object)
**What it is:** the typed state you pass through nodes/edges.

**Where it lives:** only for the current graph run (unless you also checkpoint it).

**Use cases:**
- “Carry extracted fields from node A to node B”
- “Accumulate validation errors during the retry loop”

**In this repo:**
- Document graph uses state to route mapper/validator/generate/validate, but it’s effectively **one-shot**.

### 2) Checkpointer / thread-based checkpointing (durable graph memory)
**What it is:** LangGraph checkpoint storage that persists node execution state so you can resume later.

**Where it lives:** external storage used by the checkpointer (in this repo, it’s `MemorySaver`, and in production you’d use Postgres/other durable backends).

**Why it matters:** this is the correct memory for **interrupt / HITL** workflows.

**Use cases:**
- “Pause the graph until a human replies”
- “Resume conversation after an interrupt without re-running the whole graph”

**In this repo:**
- Voice contract HITL uses `MemorySaver` + `thread_id`.
- MAF calls `voice_start_voice_contract(...)`, and when the graph interrupts, you get back a `thread_id`.
- Later, MAF (or UI) calls `voice_confirm_voice_contract(thread_id=...)` to resume.

### 3) Message-history memory (buffer / summary) for chat-like graphs
**What it is:** store conversation turns and replay a window or summary into the next LLM call.

**Where it lives:** often a LangChain “memory” layer or your own store, summarized/truncated.

**Why it matters:** prevents context loss in multi-turn chat.

**Use cases:**
- “This user prefers provider X”
- “Remember the last legal entity”

**In this repo:**
- MAF is currently stateless per `/api/ask` call, so conversation memory for the central agent is expected to be added in a separate session store (next phase).
- Voice HITL memory is checkpointed by LangGraph (thread_id).

### 4) Retrieval / long-term knowledge memory (RAG)
**What it is:** vector search + documents + metadata.

**Why it matters:** you want factual memory across many sessions (“what is an AVC contract?”).

**Use cases:**
- “Look up prior templates”
- “Search rules/policies”

**In this repo:**
- Document field mapping is closer to LLM mapping + validation than classic vector RAG.
- Long-term semantic memory would be an add-on if you later want recall across historical runs.

## Part B — MAF “memory” options (what to use + why)

MAF is an orchestrator: it chooses which MCP tools to call and then synthesizes an answer.

### 1) Session memory (central agent conversational context)
**What it is:** persist a compact set of messages and “last tool outcomes” per `session_id`.

**Where it lives:** repo currently adds/uses SQLite `SessionStore` for `session_id`, `user_id`, `user_email`, and request metadata.

**Why it matters:** for multi-turn `/api/ask` follow-ups like “use last run results to summarize what you validated”.

**In this repo (Phase 1):**
- A session id is created/reused for document / voice / MAF calls.
- This is the base you’ll extend with message history + “last_flows” summaries.

### 2) Specialist checkpoint memory (voice HITL) — not inside MAF
**What it is:** durable state for the voice graph.

**Where it lives:** LangGraph checkpointer with `thread_id`.

**Why it matters:** it’s the safe way to manage “human confirmation” steps.

**In this repo:**
- Confirm uses `thread_id` returned by the voice tool response.

### 3) Artifact pointers instead of storing blobs
**What it is:** keep job/contract IDs and file paths rather than the full DOCX/transcript in chat context.

**Why it matters:** prevents token blow-up and keeps a clean “source of truth”.

**In this repo:**
- Document jobs and voice contracts are persisted (SQLite + filesystem).
- Session memory should store pointers + short summaries.

## Part C — Recommended mapping: “What memory for what user feature?”

| Feature you want | Best memory choice | Owner in this repo |
|---|---|---|
| Multi-turn central agent asks | Session memory (messages + compact tool facts) | MAF (SessionStore) |
| Voice pause/resume with user confirmation | LangGraph checkpointer + `thread_id` | voice LangGraph |
| Retry / routing inside doc generation | In-graph state + retry counter | document LangGraph |
| Remember facts across many users/sessions | RAG / retrieval | new component (optional) |
| Don’t re-send whole payloads | Artifact pointers + refresh via tools | session + artifact stores |

## Part D — Quick interview sentence
“LangGraph memory is for stateful graph execution and HITL resume via checkpointing; MAF memory is for conversational context across `/api/ask` turns via session storage. MCP is just the tool boundary.”

