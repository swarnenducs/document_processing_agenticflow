# Architecture changes — central-agent session context

**Goal:** Use other-flow (MCP) responses as context for the central agent and allow follow-up prompting over them.  
**Status:** Design only (not implemented).  
**Related:** [../maf-basic/04-memory-and-sessions.md](../maf-basic/04-memory-and-sessions.md)

---

## 1. Current vs target architecture

### Today (stateless MAF)

```text
UI ──POST /api/ask {message}──► ip_api ──► MAF :8003
                                              │ one-shot agent.run(message)
                                              ├─► document MCP
                                              └─► voice MCP
                                    (tool results discarded after response text)
```

### Target (session-aware central agent)

```text
UI (holds session_id)
  │
  ▼
POST /api/ask { message, session_id }
  │
  ▼
ip_api (proxy; optional auth/user_id)
  │
  ▼
MAF Orchestrator
  │  1. load SessionStore[session_id]
  │  2. build prompt = instructions + running_summary + last_flows + recent_messages + user
  │  3. agent.run(...) → tools → MCPs (unchanged)
  │  4. extract compact flow facts from tool results
  │  5. append messages; maybe summarize if over budget
  │  6. save SessionStore; return { text, session_id, last_flows? }
  │
  ├─► document MCP   (unchanged contracts)
  └─► voice MCP      (HITL still uses thread_id inside voice graph)

ArtifactStore (jobs / contracts / files)  ← already exists (SQLite/FS)
SessionStore (NEW) ← Redis or SQLite/Postgres
```

**Important:** Document/voice MCP architecture stays. Change is mainly **around MAF + API + UI + a new session store**.

---

## 2. What changes (by component)

| Component | Change required? | What |
|---|---|---|
| **SessionStore (new)** | **Yes — new building block** | Persist `session_id` → messages, `running_summary`, `last_flows[]`, timestamps |
| **central-agentic-flow** | **Yes — core** | Load/save session; inject context; post-process tool results; context-window policy |
| **ip_api `/api/ask`** | **Yes — thin** | Accept/return `session_id`; proxy through |
| **UI Central Agent tab** | **Yes — thin** | Keep `session_id` in Gradio state; send on every ask; optional “New session” |
| **document-processing-mcp** | **No (or minimal)** | Keep returning structured JSON; optional slightly richer `summary` fields |
| **voice_enable_mcp** | **No (or minimal)** | Keep `thread_id` / HITL; session only stores pointers |
| **Artifact storage (jobs/contracts)** | **Reuse** | Canonical files/ids; session stores pointers, not blobs |
| **Prompts** | **Yes — small** | Update `orchestrator_instructions.md` for “use last_flows / don’t invent” |
| **Docker / compose** | **Optional** | Redis (or shared SQLite path) for SessionStore |
| **Auth** | **Later** | Bind `session_id` to `user_id` so sessions aren’t guessable |

---

## 3. New logical module (inside MAF)

```text
central-agentic-flow/
  session/
    store.py          # get/put/delete session
    models.py         # SessionState, FlowFact, Message
    context_builder.py  # summary + last_flows + window → prompt parts
    window_policy.py    # token budget, summarize trigger
  orchestrator.py     # ask_maf(message, session_id=...) wired to above
```

### SessionState (conceptual)

```text
SessionState
  session_id
  user_id? 
  messages[]          # role + content (windowed)
  running_summary     # compressed older context
  last_flows[]        # compact tool outcomes (flow, tool, ok, ids, short summary)
  updated_at
```

---

## 4. API contract changes

| Endpoint | Today | After |
|---|---|---|
| `POST /ask` (MAF) & `POST /api/ask` | `{ message, instructions? }` | + optional `session_id` (create if missing) |
| Response | `{ text, response_id }` | + `session_id`, optional `last_flows` / `context_tokens_estimate` |
| Optional | — | `DELETE /sessions/{id}`, `GET /sessions/{id}` for debug |

No change required to MCP tool URLs or `/api/v1/documents/*` / voice REST for Phase 1.

---

## 5. Data-flow sequence (one follow-up turn)

```text
1. UI sends session_id + "Summarize the validation score from the last document run"
2. MAF loads SessionState.last_flows (document fact with path + summary)
3. Context builder injects that into the prompt (not the full DOCX)
4. LLM answers from context; or calls document_* again if detail missing
5. MAF appends assistant message; saves session
```

If voice confirm:

```text
Session.last_flows has thread_id
→ MAF calls voice_confirm_voice_contract(thread_id=...)
→ Voice MemorySaver resumes graph (unchanged)
→ New flow fact written into session
```

---

## 6. Context-window policy (architecture concern)

Owned by **MAF `window_policy`**, not by MCP:

| Rule | Owner |
|---|---|
| Max recent messages (K) | MAF session layer |
| Summarize when over token budget | MAF (+ small LLM call) |
| Truncate tool JSON before persist | MAF after each tool result |
| Canonical large payloads | Artifact store only |
| HITL graph state | Voice checkpointer only |

---

## 7. Deployment / ops changes

| Item | Notes |
|---|---|
| Persistence | Redis for multi-instance MAF; SQLite OK for single local process |
| Sticky sessions | Not needed if SessionStore is shared |
| TTL | e.g. expire sessions after 24h |
| PII | Don’t put full transcripts forever; summarize / redact |
| Observability | Log `session_id` + `xid` together (MLflow later) |

---

## 8. What you explicitly do *not* change

| Keep | Why |
|---|---|
| Separate MCP processes | Specialists stay independently deployable |
| Document one-shot LangGraph | No MAF memory inside document graph |
| Voice `MemorySaver` + `thread_id` | Different memory for HITL |
| Direct UI → `/api/v1/...` tabs | Optional parallel path; session is for Central Agent |

---

## 9. Implementation order (architecture phases)

| Phase | Architecture deliverable |
|---|---|
| **P1** | SessionStore + `session_id` on `/ask` + UI state | **Done** — SQLite `sessions` / `session_requests`; document + voice + MAF; UI session/user fields |
| **P2** | Persist `last_flows` from tool results + inject into prompt | Pending |
| **P3** | Window + running summary policy | Pending |
| **P4** | Multi-instance Redis + session TTL + user binding | Pending |

---

## 10. One-line architecture summary

> Add a **SessionStore beside MAF**, extend `/ask` with **`session_id`**, teach the orchestrator to **inject compact last-flow facts + a running summary**, and keep MCP/LangGraph checkpoints as they are — specialists produce artifacts; the central agent remembers **dialogue + pointers**.
