# Token consumption by component (estimate)

This is an **order-of-magnitude estimate**, not a bill. Numbers come from prompt files, the character clip limits in code, default `max_retries`, and `*_MAX_TOKENS`. Real usage depends on template size, JSON size, retry, chat history, and the provider’s tokenizer.

**Rule of thumb used here:** English / JSON ≈ **4 characters ≈ 1 token**. Structured-output schemas add extra input tokens (often 200–800) that are included in the ranges below.

**Who actually calls an LLM**

| Component | LLM / model calls? | Typical role |
|-----------|--------------------|--------------|
| `document-processing-mcp` (:8001) | **Yes** — this is where document tokens are spent | Mapper + two validator/critic calls |
| `voice_enable_mcp` (:8002) | **Yes** — small intent + confirm calls | Mapper-role LLM (`MAPPER_*`) |
| `central-agentic-flow` MAF (:8003) | **Yes** — chat orchestrator only | `MAF_MODEL_ID` |
| `ip_api` (:8000) | **No chat/mapper/validator.** Speech-to-text is billed **per audio minute**, not tokens | Whisper / Groq Whisper |
| `UI` (:7860) | **No** | HTTP client only |

Document jobs submitted through the API or UI still burn tokens **inside document MCP**, not inside `ip_api`. Voice REST that goes MAF → voice MCP burns tokens **inside voice MCP** (plus MAF if `/ask` is used).

---

## 1. Document MCP (`document-processing-mcp`)

LangGraph path (defaults): extract XML (no LLM) → **extraction critic** → **mapper** → generate .docx (no LLM) → **document critic**. If validation fails and `max_retries=1` (default), **mapper + generate + document critic** run again. Extraction critic is **not** retried.

### 1.1 LLM calls per job

Payloads are compacted: mapper no longer dumps full block text (occurrences carry a short `ctx`), JSON arrays are sampled (`_n` / `_keys` / `_sample`), and critic clips are tighter.

| Step | Role / env | Input bound in code | Completion cap | Est. input tokens | Est. output tokens |
|------|------------|---------------------|----------------|-------------------|--------------------|
| Extraction critic | validator (`VALIDATOR_*`) | placeholders 800 chars, blocks 1 800, tables 800 + short system | `VALIDATOR_MAX_TOKENS` default **1024** | 700–1 500 | 120–350 |
| Mapper (LLM #1) | mapper (`MAPPER_*`) | placeholders 1 500, occurrences 2 800, tables 1 500, compact blocks 1 200, sampled JSON 4 000 + ~400-token system | `MAPPER_MAX_TOKENS` (unset = provider default) | 2 500–5 500 | 400–1 500 |
| Document critic (LLM #2) | validator | template 700, generated 700, snippets 900, JSON 900, mappings 1 200, unmapped/leftovers 300 each | **1024** | 1 200–2 200 | 150–500 |

Mapper is still the expensive call. Hard ceiling is now ~11 k characters of payload (~2.8k tokens) plus the system prompt, down from ~26 k characters before compaction.

### 1.2 Per-job totals

| Scenario | LLM round-trips | Est. **input** | Est. **output** | Est. **total** |
|----------|-----------------|----------------|-----------------|----------------|
| Small invoice, no retry, both critics on | 3 | 4.5k–8k | 0.7k–1.8k | **5.5k–10k** |
| Sample contract JSON (`dummy_products.json`), no retry | 3 | 5.5k–9k | 0.8k–2k | **6.5k–11k** |
| Same job, validation retry once (`max_retries=1`) | 5 (extraction + 2× mapper + 2× critic) | 9k–16k | 1.3k–4k | **10k–20k** |
| `skip_extraction_validation=true` | 2 | 4k–8k | 0.6k–2k | **4.5k–10k** |
| `skip_validation=true` (skip document critic **and** retry) | 2 (extraction + mapper) | 3.2k–7k | 0.5k–1.9k | **4k–9k** |
| Both skips | 1 (mapper only) | 2.5k–5.5k | 0.4k–1.5k | **3k–7k** |
| Mapper credentials missing | 0 LLM (deterministic fallback) | 0 | 0 | **0** |

Worked example (contract template, happy path, mid of the ranges): **~7 000 input + 1 200 output ≈ 8 200 tokens / job** (was ~14 000 before payload compaction). Mapping still uses placeholder keys, short occurrence `ctx`, table headers, and JSON paths; critics still run unless you skip them.

Optional cheaper mapper path (opt-in `optimized_flow` + [llm_optimization.json](../document-processing-mcp/config/llm_optimization.json)): [DOCUMENT_LLM_OPTIMIZATION.md](DOCUMENT_LLM_OPTIMIZATION.md). Off by default.

---

## 2. Voice MCP (`voice_enable_mcp`)

LLM is **not** used for catalog lookup or .docx generation. Only two small structured calls (same `MAPPER_*` credentials as the document mapper if you share keys):

| Step | When | Static prompt | Variable input | Est. total tokens |
|------|------|---------------|----------------|-------------------|
| Intent parse | `start_voice_contract` | ~210 | transcript (typically 20–80 words ≈ 30–120 tokens) | **300–700** |
| Confirm parse | `confirm_voice_contract` | ~190 | “yes” / a reference | **250–500** |
| List contracts | no LLM | — | — | **0** |
| Unrelated chat (“what’s the weather”) | intent only, then stop | — | — | **300–700** |
| No mapper credentials | regex fallback | — | — | **0** |

Full create-contract with HITL: **~550–1 200 tokens** of LLM. That is an order of magnitude cheaper than one document job.

---

## 3. MAF / central agent (`central-agentic-flow`)

`POST /ask` (and Foundry Responses chat) uses `MAF_MODEL_ID`. Document/voice MCP tools are **jobs-only** in `mcp_registry.yml`, so a normal chat turn should **not** pull the document pipeline into the orchestrator.

| Piece | Est. tokens |
|-------|-------------|
| Orchestrator instructions | ~150–250 |
| Tool catalog for **ask-mode** MCPs (business MCP if `BUSINESS_MCP_URL` is set) | 0–2 000 (0 if no ask MCP) |
| User message | 20–400 typical |
| One tool round-trip (model → tool JSON → model) | extra 200–1 500 |
| Final short answer | 50–400 |

| Scenario | Est. total / turn |
|----------|-------------------|
| Short Q&A, no tools | **400–1 200** |
| One ask-MCP tool call | **1 500–4 000** |
| Multi-tool / long session (history grows) | **4k–15k+** (history is the risk) |

`POST /invoke` (document/voice jobs) is **deterministic**: MAF does **not** spend chat tokens on that path. Tokens are spent in the MCP that runs the job.

---

## 4. Gateway (`ip_api`) and UI

| Path | Tokens? | What you pay instead |
|------|---------|----------------------|
| `POST /api/v1/documents/jobs` | No LLM in the API process | Document MCP job (section 1) |
| `POST /api/ask` | No LLM in the API process | MAF turn (section 3) |
| `POST /api/v1/audio/transcribe` | No chat tokens | **Speech-to-text minutes** |
| `POST /api/v1/voice/contract/from-audio` | STT here + voice MCP (+ optional MAF invoke) | Minutes + section 2 |
| Admin template CRUD, health, SQLite, blob | 0 | Storage / SQL only |
| Gradio UI | 0 | Same as the API calls it makes |

### Speech-to-text (not tokens)

OpenAI Whisper and Groq Whisper are typically billed **per minute of audio**, not per token.

| Clip | Approx. duration | OpenAI Whisper (illustrative ~\$0.006 / min) |
|------|------------------|-----------------------------------------------|
| Short utterance | 10–20 s | ~\$0.001–\$0.002 |
| 1 minute | 60 s | ~\$0.006 |
| 5 minutes | 5 min | ~\$0.03 |

Groq is often cheaper; use the provider’s current STT price list.

---

## 5. Illustrative cost (chat tokens only)

Provider list prices change. Plug your numbers into:

```text
cost = (input_tokens / 1_000_000) * input_USD_per_1M
     + (output_tokens / 1_000_000) * output_USD_per_1M
```

**Example only** (not a quote): if mapper input were \$0.40 / 1M and output \$1.60 / 1M (a typical mini-model band):

| Workload | Tokens | Example USD |
|----------|--------|-------------|
| One document job, no retry (~8k) | ~7k in / 1.2k out | **~$0.005** |
| Same job with one retry (~15k) | ~12k in / 2.5k out | **~$0.009** |
| One voice contract HITL (~0.8k) | ~0.6k in / 0.2k out | **~$0.0006** |
| One MAF chat, no tools (~0.8k) | ~0.6k in / 0.2k out | **~$0.0006** |
| 100 document jobs / day, no retry | ~0.82M / day | **~$0.47 / day** (~\$14 / 30-day month) |
| 1 000 document jobs / day | ~8.2M / day | **~$4.70 / day** (~\$140 / month) |

If mapper and validator use **different** models, split the table: extraction + document critic on `VALIDATOR_*`, mapper (+ voice intent) on `MAPPER_*`, chat on `MAF_*`.

---

## 6. Knobs that change the bill

| Knob | Effect |
|------|--------|
| `MAPPER_MAX_TOKENS` / `VALIDATOR_MAX_TOKENS` / `LLM_MAX_TOKENS` | Caps **completion** size (validator already defaults to 1024) |
| `DOCUMENT_MAX_RETRIES` / API `max_retries` (default 1, max 3) | Each retry repeats **mapper + document critic** |
| `optimized_flow` / `DOCUMENT_LLM_OPTIMIZATION_ENABLED` | Optional cheaper mapper first; see [DOCUMENT_LLM_OPTIMIZATION.md](DOCUMENT_LLM_OPTIMIZATION.md) |
| `skip_validation` / `skip_extraction_validation` | Drops one critic (and retry if document critic is skipped) |
| `DOCUMENT_MARKER_SYNTHESIS_ENABLED` | `false` skips the extra mapper call that stamps tags onto unmarked Word files |
| Template / JSON size | Mapper samples JSON arrays; payload is clipped to ~11 k characters |
| Chat history on MAF / Foundry | Unbounded unless you truncate session context |
| Missing API keys | Mapper/voice fall back to rules → **0 LLM tokens** (quality drops) |

Trace logs (`TRACE_LOG_MAX_CHARS`) store request/response text in SQLite; they do **not** add model tokens.

---

## 7. How to measure for real

Estimates above are from code limits. For a real bill:

1. Turn on provider usage dashboards (OpenAI / Azure / Groq) filtered by API key or deployment.
2. Use xid traces (`GET /api/v1/traces/{xid}`) — `call_logs` rows with `kind` LLM include latency and payloads (truncated).
3. Count jobs: `document_jobs` × ~8k tokens (happy path after mapper compaction), plus retries from `validation` failures.

---

## 8. How we justify the spend

Token use is justified when **each LLM call has a job that code cannot do**, and **everything else stays off the model**.

| Call | Why it exists | What we do *not* send to an LLM |
|------|----------------|----------------------------------|
| Mapper | Semantic match: JSON paths ↔ template placeholders / table headers. Rules miss `<XX>` vs admin-fee `<X>` without context. | Word XML rewrite, file I/O, SQL, blob, UI |
| Extraction critic | Confidence that XML extraction found the placeholders (QA on step 1) | The .docx zip itself |
| Document critic | Independent judge: leftover tokens, wrong fills (LLM-as-judge, different role) | Full generated XML |
| Voice intent / confirm | Short structured parse of speech/text | Catalog lookup, contract file write |
| MAF `/ask` | Chat routing to **ask-mode** tools only | Document/voice **jobs** (`POST /invoke` is not a chat loop) |

**Architecture arguments (interview / stakeholder):**

1. **Pay per job, not per click.** Gateway and UI never call the mapper. One document job ≈ **8k tokens** (~\$0.005 at the illustrative mini-model prices in section 5). That is cheaper than a human re-checking a filled contract.
2. **Deterministic where possible.** Style extract + .docx generate are XML, not tokens. Voice catalog lookup is JSON, not tokens.
3. **Bounded prompts.** Mapper payload is clipped (~11k characters). JSON arrays are sampled. Duplicate block dumps were removed. Validator completion is capped at **1024** tokens.
4. **Two roles, not one fat call.** Mapper decides fills; validator only scores. A retry (`max_retries=1`) is capped — not an unbounded agent loop.
5. **Chat cannot accidentally run the document pipeline.** Registry `invoke.modes: [jobs]` keeps generate-document off `/ask`.
6. **Prove it.** `GET /api/v1/traces/{xid}` shows each LLM row (kind, name, latency, truncated payload). Provider dashboards should match `document_jobs × ~8k` on a quiet day.

**One-sentence pitch:** we spend ~8k tokens to map and QA a contract because the alternative is either a wrong fill (business risk) or a human editor; we do not spend tokens on XML, storage, or the HTTP gateway.

