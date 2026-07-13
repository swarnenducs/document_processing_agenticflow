# Developer Guide — Interview Prep

Use this guide to **understand, demo, and explain** the Document Processing Agentic Flow codebase in interviews. It is oriented around *what interviewers ask* and *how this repo answers those questions*.

For setup and API reference, see [README.md](README.md). For Azure Web Apps + GitHub Actions, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md). This document focuses on **architecture, design tradeoffs, and talking points**.

---

## 1. Elevator pitch (30–60 seconds)

> This project fills a Word `.docx` template from JSON while **preserving original OOXML styles**.  
> Orchestration is a **LangGraph state machine**: extract styles → map fields with **LLM #1 (OpenAI)** → generate the document → validate with an **independent LLM #2 (Groq)** → aggregate **confidence as percentages**.  
> The same services power a **CLI**, **async FastAPI jobs** (SQLite + filesystem), a **Gradio UI**, and an optional **tool-calling agent**. Without API keys, deterministic rules still run so demos and tests stay reliable.

**One-liner variant:** “LangGraph document pipeline with dual-LLM map/validate, style-preserving OOXML generation, and job-based FastAPI + Gradio.”

---

## 2. What problem it solves

| Problem | How this repo addresses it |
|---------|----------------------------|
| Fill Word templates from structured data | JSON → placeholder + table fill → new `.docx` |
| Keep fonts, bold, table look | Copy the `.docx` ZIP; rewrite `word/document.xml` carefully |
| Mapping is fuzzy (labels ≠ JSON keys) | LLM #1 semantic mapping; no hardcoded business aliases |
| Trust the output | LLM #2 critic + rule checks + weighted confidence % |
| Ship beyond a script | CLI + FastAPI jobs + Gradio + optional agent |

---

## 3. Mental model (draw this on a whiteboard)

```text
                    ┌─────────────────────────────────────────┐
                    │         DocumentProcessingState         │
                    │  paths, json_data, extracted, mapping,  │
                    │  generation, validation, confidence…    │
                    └─────────────────────────────────────────┘
                                         │
  START → load_data → extract_styles → map_fields → generate → validate
                              │              ▲                    │
                              │              │   bump_retry       │
                              │              └──────── retry ─────┤
                              │                                   ▼
                              └─────────────────────────────→ finalize → END

  Surfaces:
    CLI (doc-agent)  │  FastAPI jobs (doc-api)  │  Gradio (doc-ui)
                     │  BackgroundTasks + SQLite + files
                     └─ Agent mode: LLM picks tools from tools.py
```

**Interview tip:** Emphasize *shared services*, *thin LangGraph nodes*, and *multiple entry points* (CLI / API / UI / agent) over the same core.

---

## 4. Repo map (what to open first)

| Path | Why it matters in an interview |
|------|--------------------------------|
| `graph.py` | LangGraph wiring, conditional edges, retry |
| `nodes/pipeline.py` | Thin nodes that call services |
| `models/state.py` | Shared graph state (`TypedDict`) |
| `models/schemas.py` | Domain models (`MappingResult`, `TableFillPlan`, `ConfidenceReport`) |
| `services/llm_factory.py` | Dual-LLM configuration |
| `services/placeholders.py` | Token **syntax** only — design choice |
| `services/field_mapper.py` | LLM #1 + rule fallback |
| `services/document_generator.py` | OOXML rewrite + `table_fills` |
| `services/document_validator.py` | LLM #2 + rules |
| `services/confidence.py` / `scoring.py` | Weighted overall + `%` for UI |
| `api/routes.py` + `storage/job_store.py` | Async jobs, SQLite, files |
| `ui/gradio_app.py` | Product surface; talks to API only |
| `tools.py` + `agent.py` | Agent mode vs fixed pipeline |
| `tests/` | How you prove it without live keys |

---

## 5. Pipeline deep dive (be ready to walk node by node)

### 5.1 `load_data`
- Loads JSON from `data_path` into state.
- Sets defaults: `max_retries=1`, `validation_threshold=0.7`.

### 5.2 `extract_styles` → `style_extractor.extract_word_styles`
- Treats `.docx` as a ZIP (OOXML).
- Reads styles / content blocks / placeholders.
- Keeps raw paragraph/run XML where useful so generation can preserve formatting.

### 5.3 `map_fields` → `field_mapper.map_json_to_template` (**LLM #1**)
Produces:
1. **Scalar mappings** — placeholder → JSON path/value + confidence  
2. **`table_fills`** — which JSON array fills which table; header → object field  

**Fallback:** exact / generic string variants (`snake_case` ↔ `camelCase`) when no API key.  
**Not used:** hardcoded product/date synonym dictionaries.

### 5.4 `generate_document` → `document_generator.generate_styled_document`
- Copies the template package.
- Replaces placeholders in `document.xml`.
- Expands tables from LLM `table_fills` plans (clone header-row style, insert rows).
- Computes **integrity** (e.g. leftover placeholders).

### 5.5 `validate_document` → `document_validator.validate_documents` (**LLM #2**)
- Always runs deterministic rules.
- Optionally merges critic LLM score/issues.
- On high-severity leftovers, can take `min(llm_score, rule_score)`.

### 5.6 Retry + `finalize`
- If validation fails or score &lt; threshold and retries remain → `bump_retry` → remapping.
- `finalize` attaches/ensures `ConfidenceReport`, sets `status=completed`.

**Routing helpers in `graph.py`:** `_should_continue`, `_after_validation`.

---

## 6. Dual-LLM design (high-signal talking point)

| | **LLM #1 Mapper** | **LLM #2 Validator** |
|--|-------------------|----------------------|
| Default provider | OpenAI | Groq |
| Config | `MAPPER_PROVIDER` / `MAPPER_MODEL` | `VALIDATOR_PROVIDER` / `VALIDATOR_MODEL` |
| Built-ins | `openai`, `azure_openai`, `groq`, `openai_compatible` | same |
| Injection | `register_llm_provider("name", builder)` | same |
| Factory | `get_mapper_llm()` | `get_validator_llm()` |
| Structured output | Mapping payload | Validation payload |

**Why two roles?**  
The critic should not share the same model bias as the mapper — classic *generator vs critic*.

**Provider injection:** swap Azure OpenAI / Groq / local Ollama via env, or register a custom LangChain chat model builder without rewriting the pipeline.

**Graceful degradation:** missing credentials → rules still produce a scored result (`mapper_source="rules"`, `validator_source="rules"`). Good for CI and local demos.

**Speech STT** (`speech_to_text.py`) is a separate Whisper path (OpenAI or Groq), not the map/validate pair.

---

## 7. Design decisions interviewers love

### 7.1 Placeholders = token syntax, not business fields
Supported patterns in `placeholders.py`:
- `{{field}}`, `${field}`, `«field»`, `<DATE>` / `<ACCOUNT NAME>`

Meaning of fields is decided by **LLM #1** from template + JSON context.

**Say this:** “We fixed the *token syntax*, not the *domain vocabulary*, so the same pipeline works for invoices, contracts, etc.”

### 7.2 Tables via plans, not hardcoded columns
`TableFillPlan`: `array_json_path` + columns `{ header → json_field }`.  
Generator expands rows from that plan — not a baked-in “Product Code → productCode” map.

### 7.3 Style preservation via OOXML
Do not rebuild the Word doc from scratch with a naive writer.  
Copy the ZIP, mutate `document.xml`, keep run properties where possible.

### 7.4 Confidence as percentages externally
Internally 0–1; externally `scores_pct` for CLI / API / Gradio.

Default weights (see `confidence.py`):

```text
overall ≈ 0.40*mapping + 0.25*coverage + 0.15*integrity + 0.20*validation
```

If validation is skipped, remaining weights are renormalized.

### 7.5 Structured LLM outputs (Pydantic)
Prefer `with_structured_output(...)` over free-form JSON parsing — fewer brittle parse failures.

### 7.6 BackgroundTasks vs Redis/Celery
API uses FastAPI `BackgroundTasks` + SQLite job rows + filesystem blobs.

| Fit for this project | Scale-out path |
|----------------------|----------------|
| Simple demo / portfolio | Redis + RQ / Celery / Cloud Tasks |
| Single process OK | Multi-worker durable queue |
| Poll status | Progress events / webhooks |

**Honest tradeoff:** jobs are in-process; a crash can leave `processing` orphans; not multi-node safe. Showing you *know* that is better than pretending it’s production-perfect.

### 7.7 Fixed graph vs agent mode
- **Pipeline (`graph.py`):** deterministic, best for API/CLI.
- **Agent (`agent.py` + `tools.py`):** LLM chooses tools; flexible, less predictable, can re-run extract/map inside tools.

### 7.8 Layering
```text
UI / CLI / API  →  graph or agent  →  thin nodes / tools  →  services  →  OOXML / LLMs / storage
```

---

## 8. API & storage (systems design slice)

### Storage split
```text
SQLite (metadata)     SQLITE_DATABASE_PATH  → document_jobs, transcription_jobs
Filesystem (blobs)    STORAGE_BASE_PATH
  jobs/{job_id}/template.docx | data.json | output.docx
  audio/{id}/input.<ext>
```

### Job lifecycle
1. `POST /api/v1/documents/jobs` → save files, insert row, `202` + `job_id`  
2. Background: `pipeline_runner.run_document_job` → `build_graph().invoke(...)`  
3. `GET .../jobs/{id}` → status + confidence + `scores_pct`  
4. `GET .../download` → `.docx` when ready  

Also: health, delete job, audio transcribe + fetch transcript.

**Known gap:** `JOB_TTL_HOURS` is configured but cleanup is not implemented — good “what would you add next?” answer.

---

## 9. Gradio UI

- Tab 1: **Generate Document** — upload template + JSON (or paste), poll job, download, score report.  
- Tab 2: **Voice → Text** — mic/upload → Whisper via API.  
- UI talks to FastAPI only (`API_BASE_URL`); does **not** run LangGraph in-process.

Start everything: `uv run doc-app` or `./run.sh`.

---

## 10. How to prep in one evening

### Step A — Run the happy path (30 min)
```bash
uv sync
cp .env.example .env   # keys optional for rule path; better with keys for LLM story
uv run python scripts/create_sample_template.py
uv run pytest
uv run doc-agent \
  --template samples/templates/invoice_template.docx \
  --data samples/data/invoice.json \
  --output samples/output/invoice_filled.docx \
  --dump-confidence samples/output/confidence.json
uv run doc-app   # open UI; generate + voice tabs
```

### Step B — Read in this order (60–90 min)
1. `graph.py` + `nodes/pipeline.py`  
2. `field_mapper.py` + `placeholders.py`  
3. `document_generator.py` (table expand)  
4. `document_validator.py` + `confidence.py`  
5. `api/routes.py` + `job_store.py`  
6. `llm_factory.py`  

### Step C — Practice aloud (20 min)
Explain the elevator pitch, then whiteboard the graph, then answer 3 Q&As from §12.

---

## 11. Demo script (5–7 minutes)

1. **Problem** — “Templates + JSON; styles must survive; mapping isn’t exact.”  
2. **Architecture** — Draw LangGraph + dual LLM + scores.  
3. **Live CLI or UI** — Invoice sample; show output `.docx` and confidence %.  
4. **Code jump** — Show `table_fills` in schemas + expand in generator.  
5. **API** — Mention `202` job + poll + download; SQLite vs files.  
6. **Tradeoffs** — BackgroundTasks vs queue; rules fallback; no auth / TTL cleanup.  
7. **Next steps** — Job TTL worker, Redis queue, auth, richer layout validation.

Optional stretch: contract template with `<DATE>`, `<ACCOUNT NAME>`, and a products table — show LLM-driven table fills.

---

## 12. Likely interview questions (and strong answers)

**Q: Why LangGraph instead of a plain Python script?**  
A: Explicit state, conditional edges (retry), observability of steps, same graph invocable from CLI/API; room to grow checkpoints/streaming later.

**Q: Why not hardcode field aliases?**  
A: Domain-specific dictionaries don’t generalize. We detect *syntax*; LLM (or exact-name rules) decides *semantics* from template + JSON.

**Q: How do you preserve Word formatting?**  
A: `.docx` is OOXML ZIP; we copy the package and rewrite `document.xml`, preserving run/paragraph properties where possible instead of recreating styles from scratch.

**Q: How do tables get filled?**  
A: Mapper returns `TableFillPlan` (array path + header→field). Generator clones the header row’s style and inserts data rows. No fixed product schema in code.

**Q: How do you know the document is good?**  
A: Integrity checks (leftovers), rule validation, independent critic LLM, weighted overall % exposed as `scores_pct`.

**Q: What if the LLM is down / no keys?**  
A: Rule fallbacks keep the pipeline usable for exact-name templates and for tests (`conftest` clears keys).

**Q: Graph vs agent — when use which?**  
A: Graph for production-ish deterministic jobs; agent for exploratory NL orchestration over the same tools.

**Q: How would you productionize this?**  
A: Authn/z, durable queue, job TTL/cleanup, idempotency, metrics/tracing per node, prompt/version registry, human-in-the-loop on low confidence, multi-tenant storage isolation.

**Q: What are the limitations?**  
A: BackgroundTasks not distributed; placeholders split across Word runs can be tricky; validation is text-centric not visual; prompts truncate large JSON; voice is not wired into fill flow; no API auth; TTL unused.

**Q: How are tests designed?**  
A: `pytest` hits extract/map/generate/graph/API with rule fallbacks — CI does not depend on live OpenAI/Groq.

---

## 13. Concepts to be fluent in (vocabulary)

| Term | Meaning in this repo |
|------|----------------------|
| OOXML | Office Open XML — `.docx` = ZIP of XML parts |
| Placeholder | Token like `{{x}}` / `<DATE>` found in template text |
| `table_fills` | LLM plan to expand a table from a JSON array |
| Structured output | LLM returns typed Pydantic object |
| Critic / validator | Second LLM reviewing the filled doc |
| Integrity score | Deterministic post-write quality signal |
| `scores_pct` | External %-view of internal 0–1 scores |
| Conditional edge | LangGraph branch after a node (retry vs finalize) |
| BackgroundTasks | In-process async after HTTP response |
| Rule fallback | Non-LLM mapping/validation path |

---

## 14. Suggested study extensions (if interview goes deep)

1. LangGraph: checkpointers, streaming, human-in-the-loop interrupts.  
2. Word XML: `w:p`, `w:r`, `w:rPr`, split runs across placeholders.  
3. Evaluation: gold templates + JSON → score regression suite.  
4. Observability: LangSmith / OpenTelemetry around each node.  
5. Security: upload scanning, path traversal, prompt injection via template text.

---

## 15. Cheat sheet — commands

```bash
uv sync
uv run pytest
uv run python scripts/create_sample_template.py
uv run doc-agent --template ... --data ... --output ...
uv run doc-api          # http://localhost:8000/docs
uv run doc-ui           # http://127.0.0.1:7860
uv run doc-app          # API + UI
./run.sh
```

---

## 16. Closing line you can reuse

> “I built this as a **service-oriented LangGraph pipeline**: style-aware OOXML generation, **LLM mapping with planned table fills**, an **independent critic**, and **confidence percentages**, exposed through CLI, async jobs, and Gradio — with rule fallbacks so it stays demoable and testable without live keys.”

That sentence covers architecture, AI design, product surfaces, and engineering maturity in one breath.
