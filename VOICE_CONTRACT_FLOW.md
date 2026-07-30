# How Voice → Contract Works

End-to-end guide for the **Voice → Contract** feature: speech (optional) → transcript → **LangGraph agent** → human confirmation → dummy contract files + SQLite.

> Orchestration is always LangGraph. Nodes may call SQLite today or HTTP APIs later; the agent shape stays the same.

---

## Overview (one picture)

```text
┌──────────────┐     ┌─────────────────┐     ┌──────────────────────────────┐
│ Mic / upload │────▶│ Speech-to-text  │────▶│ Transcript (plain text)      │
│ or typed chat│     │ (Groq/OpenAI/…) │     │                              │
└──────────────┘     └─────────────────┘     └──────────────┬───────────────┘
                                                            │
                                                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ LangGraph voice agent (`voice_graph.py`)                                 │
│                                                                          │
│  START → parse_intent → fetch_legal_entity → fetch_pricelist             │
│            │                  │                    │                     │
│            └──── reject ──────┴──── reject ────────┘                     │
│                               ▼                                          │
│                    await_confirmation  ←── interrupt() HITL              │
│                               │                                          │
│                    (user says yes / CR-1001 via thread_id)               │
│                               ▼                                          │
│                    generate_contract → END                               │
└──────────────────────────────────────────────────────────────────────────┘
                                                            │
                                                            ▼
                                              API persists files + SQLite row
```

**Surfaces**

| Surface | Role |
|---------|------|
| Gradio **Voice → Contract** tab | Chat + optional mic; stores `thread_id` between turns |
| REST `/api/v1/voice/*` | Same agent; confirm with `thread_id` |
| REST `/api/v1/audio/transcribe` | Speech only (no contract logic) |

---

## Step-by-step flow

### 1. Get natural-language text

Two ways into the same agent:

| Path | What happens |
|------|----------------|
| **Type in chat** | Text goes straight to the agent (no speech). |
| **Speak / upload audio** | `speech_to_text` → transcript → agent. On connection errors, other configured providers are tried. |

Speech is optional. Contract logic never requires a microphone.

Env: `SPEECH_PROVIDER=groq` (default in `.env.example`), or `openai` / `azure_openai` / `auto`.

### 2. LangGraph agent runs

Compiled graph: `voice_graph.py` + nodes in `nodes/voice_contract.py`.  
State: `VoiceContractState` (`models/voice_state.py`).  
Checkpointer: process-local `MemorySaver` keyed by `thread_id`.

| Node | Responsibility | Data source |
|------|----------------|-------------|
| `parse_intent` | Detect create-contract; extract legal entity + contract ref | Regex / helpers |
| `fetch_legal_entity` | Load entity master (name, address, email, …) | SQLite (`legal_entities`) — swappable to API |
| `fetch_pricelist` | Match pricelist by ref (fuzzy: `CR 1001` ≈ `CR-1001`) | SQLite (`pricelists`) — swappable to API |
| `await_confirmation` | Pause with `interrupt()` until human confirms | LangGraph checkpointer |
| `generate_contract` | Write dummy `.txt` + `.docx` | Local filesystem |

Conditional edges stop early with status `rejected` and message **Please ask a relevant service.** when intent/entity/ref lookup fails.

### 3. Human-in-the-loop

When lookups succeed, the graph **interrupts** and returns:

- `status: needs_confirmation`
- `thread_id` (required to resume)
- suggested legal entity + contract reference + candidates

User replies `yes` / `confirm` or types the reference (e.g. `CR-1001`).

Resume:

```text
Command(resume={ action, text, ref })  on the same thread_id
```

Then `generate_contract` runs and the API layer saves the contract into SQLite (`voice_contracts`) and storage.

`auto_create: true` on the first API call skips the interrupt (UI does not use this).

### 4. Outputs

- Dummy contract **text** (`.txt`) and **Word** (`.docx`)
- SQLite row with paths + spoken entity/ref
- Download via UI panels or `GET /api/v1/voice/contracts/{id}/download`

---

## Exact prompts (seeded dummy data)

**Turn 1**

```text
please create contract with legal entity AVC contract reference number CR 1001
```

**Turn 2 (confirm)**

```text
yes
```

or:

```text
CR-1001
```

Also valid:

```text
Please create contract with Legal entity AVC with contract reference number CR-1001
Please create contract with Legal entity ACME with contract reference number CR-2002
```

| Legal entity | Code | Sample contract reference |
|--------------|------|---------------------------|
| AVC Trading Limited | AVC | CR-1001 |
| Acme Industrial Partners LLC | ACME | CR-2002 |

Seed file: `samples/data/contract_catalog.json` (auto-seeded into SQLite on first lookup).

---

## Try it in the UI

1. Start: `python run_both.py` (or `uv run doc-app`)
2. Open http://127.0.0.1:7860 → tab **Voice → Contract**
3. Type (or speak) the create-contract prompt
4. Review entity + reference → reply `yes`
5. Download `.txt` / `.docx` from the right-hand panels

Gradio keeps `thread_id` in chat pending state so confirm resumes the same LangGraph thread.

If mic transcription fails, type instead — same agent path.

---

## APIs

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/voice/contract` | Start agent; return matches / `needs_confirmation` + `thread_id` |
| `POST` | `/api/v1/voice/contract/confirm` | Resume interrupt (`thread_id` + `user_text`) or finalize by entity/ref |
| `POST` | `/api/v1/voice/contract/from-audio` | Transcribe audio, then same as `/voice/contract` |
| `GET` | `/api/v1/voice/contracts` | List saved contracts |
| `GET` | `/api/v1/voice/contracts/{id}` | One contract record |
| `GET` | `/api/v1/voice/contracts/{id}/download?format=txt\|docx` | Download dummy contract |
| `POST` | `/api/v1/audio/transcribe` | Speech → text only (no LangGraph) |

### Curl (HITL)

```bash
# 1) Start — capture thread_id from JSON
curl -s http://127.0.0.1:8000/api/v1/voice/contract \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"please create contract with legal entity AVC contract reference number CR 1001"}'

# 2) Resume same LangGraph thread
curl -s http://127.0.0.1:8000/api/v1/voice/contract/confirm \
  -H 'Content-Type: application/json' \
  -d '{"legal_entity":"AVC","contract_reference_number":"CR-1001","thread_id":"<THREAD_ID>","user_text":"yes"}'
```

Confirm body: `legal_entity`, `contract_reference_number`, optional `thread_id`, `user_text`, `transcript`.

---

## Storage (SQLite)

Path: `SQLITE_DATABASE_PATH` (default `./data/app.db`).

| Table | Role |
|-------|------|
| `legal_entities` | Entity master (from catalog seed) |
| `pricelists` | Pricelist per contract reference |
| `voice_contracts` | Created contracts + file paths |
| `transcription_jobs` | Optional audio transcription metadata |

Files land under `STORAGE_BASE_PATH` (voice drafts / `voice_contracts`).

---

## Code map

| File | Role |
|------|------|
| `voice_graph.py` | StateGraph, MemorySaver, `start_` / `resume_voice_contract_agent` |
| `nodes/voice_contract.py` | Node implementations + `interrupt()` |
| `models/voice_state.py` | Shared TypedDict state |
| `services/voice_contract_workflow.py` | Parse/fuzzy helpers + thin wrappers over the graph |
| `services/speech_to_text.py` | Audio → transcript |
| `storage/job_store.py` | SQLite catalog + voice contract rows |
| `api/routes.py` | REST endpoints + persist after graph completes |
| `ui/gradio_app.py` | Chat UI + `thread_id` across turns |

---

## Design notes (interview)

- **LangGraph owns the flow**; SQLite/HTTP are just tools inside nodes.
- **HITL before side effects:** `interrupt()` until confirm, then generate files.
- **`thread_id` + MemorySaver:** pause/resume across chat or API calls (process-local; multi-worker needs a shared checkpointer).
- **Fuzzy refs:** spoken `CR 1001` → `CR-1001`.
- **Same agent** behind Gradio and REST.

---

## Related docs

- [README.md](README.md) — project overview, STT endpoint
- [INTERVIEW_LANGGRAPH.md](INTERVIEW_LANGGRAPH.md) — LangGraph interview Q&A (includes voice HITL)
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — architecture walkthrough
