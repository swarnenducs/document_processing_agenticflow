# 04 — MAF memory & sessions

## What we do today

**Each `ask_maf()` call is stateless** regarding conversation history:

- New Agent context
- One `agent.run(message)`
- No durable MAF session store in this repo

If the user says “do that again” without repeating details, MAF **won’t** remember the previous ask unless the client resends context.

Voice HITL memory lives **inside voice MCP** (SQLAlchemy checkpointer), not inside MAF.  
Flow: MAF may call `voice_start_voice_contract` → gets `thread_id` → later `voice_confirm_voice_contract(thread_id=...)`.

```text
MAF (stateless turns)
   │
   │ tool call
   ▼
Voice MCP (stateful HITL via SQL checkpointer + thread_id)
```

---

## When MAF needs memory

| Scenario | Approach |
|---|---|
| Multi-turn “orchestrator chat” | Agent session / pass prior messages |
| Remember user prefs | External DB keyed by user_id |
| Long tool transcripts | Summarize tool results into session |
| Cross-ask continuity | Client stores thread or server-side session id |

### Conceptual session pattern

```python
# Pseudocode — exact MAF API may use AgentSession
session = create_session(user_id="u1")
await agent.run("Start a contract for AVC", session=session)
await agent.run("Confirm yes", session=session)  # sees prior tool results
```

Or manually:

```python
history = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
]
# pass history into the next run if the framework supports message lists
await agent.run(history + [new_user_message])
```

---

## Memory map for the whole system

| Layer | Memory now | Production upgrade |
|---|---|---|
| MAF | None (per-request) | Session / message store |
| Voice graph | SQLAlchemy checkpointer + thread_id | Official PostgresSaver if you already run Postgres |
| Document graph | None | N/A (batch) |
| Contracts / jobs | SQLite | Postgres + object storage |

**Interview one-liner:**  
“Orchestrator memory and worker checkpoint memory are different. We checkpoint voice HITL in LangGraph; MAF asks are still single-turn.”

---

## Using other-flow responses as context for the central agent

**Yes — possible.** Pattern: specialist flows (document / voice MCP) return structured results → store them as **session context** → next MAF turns (and optional re-prompting) see that context.

```text
User ask #1
  → MAF calls document_generate_document / voice_* 
  → tool JSON (paths, status, contract_id, errors, xid)
  → write into Central Agent session store
User ask #2 / follow-up prompt
  → load session (summary + recent tool facts)
  → MAF system/user context includes those facts
  → agent can answer or call more tools without re-asking everything
```

Today this repo does **not** persist MAF chat context across `/api/ask` calls — the UI/client would need to resend history, or we add a session store (below).

### What kind of memory you need (layered)

| Layer | Type | What it stores | When |
|---|---|---|---|
| **A. Working / turn memory** | In-process message list for one `agent.run` | Current user text + tool results in that turn | Already happens inside one MAF turn |
| **B. Session (short-term) memory** | Conversation buffer keyed by `session_id` / `user_id` | Prior user/assistant turns + **compact tool outcomes** | Multi-turn Central Agent chat (“prompt over that result”) |
| **C. Specialist checkpoint memory** | LangGraph SQLAlchemy checkpointer | Voice HITL graph state (`thread_id`) | Resume confirm — **not** a substitute for MAF chat memory |
| **D. Artifact / result memory** | DB or object store (jobs, contracts, file paths) | Canonical outputs (`job_id`, `output_path`, `contract_id`) | Source of truth; session only keeps **pointers + short summaries** |
| **E. Long-term / semantic (optional)** | Vector store + metadata | “Past invoice runs for Acme” | Only if you need retrieval across many old jobs (RAG-style) |

**For “use other flow response as context + prompt over it” you mainly need B + D:**  
session memory for dialogue, artifact store so you don’t paste whole DOCX/JSON into the LLM every time.

### Recommended context payload (what to inject)

Prefer **structured, small** facts over raw dumps:

```json
{
  "session_id": "s-123",
  "last_flows": [
    {
      "flow": "document",
      "tool": "document_generate_document",
      "ok": true,
      "job_or_path": "data/storage/.../out.docx",
      "xid": "...",
      "summary": "Mapped 12 fields; validation passed at 0.91"
    },
    {
      "flow": "voice",
      "tool": "voice_start_voice_contract",
      "status": "needs_confirmation",
      "thread_id": "t-9",
      "legal_entity": "AVC",
      "ref": "CR-1001"
    }
  ],
  "running_summary": "User is creating AVC contract CR-1001; doc fill already succeeded."
}
```

Then prompt: *“Given last_flows, explain validation confidence and ask to confirm the contract.”*

### How to manage the context window

| Technique | What to do |
|---|---|
| **Window** | Keep last *K* chat turns only (e.g. 6–12) |
| **Summarize** | Periodically compress older turns + tool JSON into `running_summary` (small LLM call or rule-based) |
| **Pointers, not blobs** | Store `path` / `job_id` / `contract_id`; re-fetch via tools if the model needs details |
| **Tool-result truncation** | Cap each tool payload (e.g. 1–2 KB) before appending to history |
| **Role split** | System: instructions + summary; User: latest ask; Tools: fresh calls — don’t replay every past tool full body |
| **Budget tokens** | Reserve e.g. 30% system/summary, 40% recent turns, 30% new tool I/O |
| **Don’t use RAG for last turn** | Last flow result = session artifact, not vector search (unless corpus is huge) |
| **Specialist HITL separate** | Keep `thread_id` in session; call `voice_confirm_*` — don’t try to “remember” graph state only in chat text |

### Implementation sketch (not in repo yet)

1. Add `session_id` to `POST /api/ask`.  
2. Persist `{messages, last_flows, running_summary}` (Redis / SQLite / Postgres).  
3. On each ask: load session → build prompt context → `agent.run` → append assistant + new tool facts → maybe summarize if over token budget.  
4. UI Central Agent tab: keep `gr.State(session_id)` and send it with every message.

```text
Context window policy (simple):
  if token_estimate(session) > MAX:
      running_summary = summarize(old_messages + old_tool_facts)
      messages = last_K_messages
      last_flows = last_N_flow_summaries   # not full JSON
```

### Interview one-liner

> “We keep specialist HITL in LangGraph checkpoints, canonical outputs in the job/contract store, and a **session memory** on the central agent that holds a running summary plus compact last-flow facts so we can prompt over prior results without blowing the context window.”

Next: [05-interview-qa.md](05-interview-qa.md)
