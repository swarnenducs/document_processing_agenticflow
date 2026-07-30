# LangGraph Interview Preparation

Focused prep for **LangGraph / LangChain agent** interviews, mapped to this repo.  
For full product architecture (FastAPI, Gradio, OOXML), see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

---

## 1. Elevator pitch (this project)

> We use **LangGraph as a typed state machine** for a document pipeline: load JSON → extract Word styles → **LLM #1 maps** fields → generate `.docx` → **LLM #2 validates** → finalize, with a **conditional retry** if validation fails.  
> Providers/models are **dynamic via env + an injectable factory** (`MAPPER_PROVIDER` / `VALIDATOR_PROVIDER`), not hardcoded.  
> An optional **tool-calling agent** (`create_agent`) can orchestrate the same steps as tools.

---

## 2. Core LangGraph concepts (must-know)

| Concept | What to say | Where in this repo |
|--------|-------------|--------------------|
| **State** | Shared typed bag of data every node reads/writes | `models/state.py` → `DocumentProcessingState` |
| **Node** | Pure-ish function: `state → partial state update` | `nodes/pipeline.py` |
| **Edge** | Fixed next step | `graph.add_edge(...)` in `graph.py` |
| **Conditional edge** | Route by a function over state | `_should_continue`, `_after_validation` |
| **START / END** | Graph entry/exit sentinels | `langgraph.graph` |
| **Compile** | Build an executable app | `graph.compile()` → `build_graph()` |
| **Invoke** | Run once with an input state dict | CLI / `pipeline_runner` / API job |
| **Retry loop** | Conditional edge back to an earlier node | `validate → bump_retry → map_fields` |

### Whiteboard shape (memorize)

```text
START → load_data → extract_styles → map_fields → generate → validate
                         │                              │
                         └─ on fail → END               ├─ pass → finalize → END
                                                        └─ fail + retries left
                                                              → bump_retry → map_fields
```

**Talking point:** LangGraph shines when control flow is **explicit** (retry, skip validation, early stop) — not buried in nested `if` inside one giant LLM call.

---

## 3. State design (interview favorite)

**Why TypedDict / schema state?**

- Nodes stay small and testable.
- Interviewers look for: *what belongs in state vs side effects?*
- We keep **paths + artifacts** in state (`extracted`, `mapping`, `generation`, `validation`, `confidence`) and **errors/status** for routing.

**Good answer pattern:**

> “State is the contract between nodes. Side effects (disk writes, LLM calls) happen inside services; nodes only orchestrate and update state.”

---

## 4. Conditional edges & retry (be ready to code this)

In this repo (`graph.py`):

1. After most nodes: if `status == "failed"` → **END**, else continue.
2. After validation:
   - failed hard → stop  
   - score below threshold and `retry_count < max_retries` → **retry**  
   - else → **finalize**

**Interview follow-ups:**

| Question | Strong answer |
|----------|----------------|
| Why not infinite retry? | Cap with `max_retries`; bump counter in a dedicated node |
| Why a separate `bump_retry` node? | Keeps routing pure; state mutation is explicit |
| Checkpointing? | Not required for this batch job; would add for long human-in-the-loop flows |

---

## 5. Pipeline mode vs agent mode

| Mode | Pattern | File |
|------|---------|------|
| **Pipeline** | Fixed graph: you own the order | `graph.py` + `nodes/pipeline.py` |
| **Agent** | LLM chooses tools | `agent.py` + `tools.py` |

**When to use which (classic interview question):**

- **Pipeline:** deterministic business process, auditability, cost control, retries you define.
- **Agent:** open-ended user instructions, unknown step order, tool discovery.

This project supports **both** over the same services — strong design talking point.

---

## 6. Dynamic model / provider selection

### What interviewers mean by “dynamic init”

In modern LangChain, people often cite:

```python
from langchain.chat_models import init_chat_model

llm = init_chat_model("openai:gpt-4o")           # provider:model string
# or
llm = init_chat_model(model="gpt-4o", model_provider="openai")
```

That **`init_chat_model`** helper picks the chat model class from a provider string at runtime.

LangGraph itself does **not** require a special “init method” for models; models are usually:

1. Built outside and passed into nodes/agents, or  
2. Built inside a node from **config / env**, or  
3. Created via **`init_chat_model`** (LangChain) for a one-liner provider switch.

### What *this* repo implemented

| Approach | Implemented? | How |
|----------|--------------|-----|
| Hardcoded one model in graph | No | — |
| Env-driven provider + model per **role** | **Yes** | `MAPPER_*`, `VALIDATOR_*`, `AGENT_*` |
| Compact `provider:model` ids | **Yes** | `MAPPER_MODEL_ID=azure_openai:gpt-5-mini` |
| LangChain `init_chat_model(...)` | **Yes** | Built-ins in `llm_factory._build_via_init_chat_model` |
| Injectable custom providers | **Yes** | `register_llm_provider(...)` |
| Runtime override for agent model name | **Yes** | `build_agent(model_name=...)` |
| Per-invoke model via LangGraph `config["configurable"]` | **Not used** | Optional follow-on |

**Interview answer:**

> “We resolve each role from env (or `MAPPER_MODEL_ID=provider:model`), then build the chat model with LangChain’s **`init_chat_model`**. Azure Foundry v1 still goes through the OpenAI-compatible path inside that helper. Custom vendors use `register_llm_provider`.”

### Why a custom factory is defensible

- Two roles with **different** providers at once (mapper ≠ validator).  
- Azure AI Foundry (`…/openai/v1`) vs classic Azure OpenAI.  
- Explicit availability checks for `/health` and UI.  
- Easy to explain: *factory pattern + strategy per provider*.

### Optional next step: per-invoke configurable model

```text
graph.invoke(state, config={"configurable": {"mapper_model": "groq:llama-3.3-70b"}})
# node reads RunnableConfig and calls init_chat_model(...)
```

Today, selection is env / `*_MODEL_ID` at process start (plus agent `model_name` override).

---

## 7. Dual-LLM design (generator vs critic)

| Role | LLM # | Typical provider here | Responsibility |
|------|-------|----------------------|----------------|
| Mapper | 1 | Azure OpenAI / Foundry | JSON → placeholders + table fills |
| Validator | 2 | Groq | Independent critic vs template + JSON + output |
| Agent (optional) | orchestrator | Usually same as mapper | Picks tools |

**Why two models?** Reduce shared bias; critic should not rubber-stamp the mapper.  
**Why LangGraph?** Validation score drives **retry routing**, not just a log line.

---

## 8. Likely interview questions (Q → short A)

**Q: What is LangGraph vs LangChain?**  
A: LangChain = models, prompts, tools, LCEL. LangGraph = durable/explicit **graph orchestration** over state (cycles, branches, persistence).

**Q: Why not a single Python script with if/else?**  
A: Graph makes control flow visible, testable, and Studio-debuggable (`app = build_graph()`).

**Q: How do you handle failures?**  
A: Nodes set `status`/`errors`; conditional edges stop or retry; API stores job status in SQLite.

**Q: Where do LLM calls live?**  
A: In **services** (`field_mapper`, `document_validator`), not inside fat graph nodes — nodes stay thin.

**Q: How is the model chosen?**  
A: Env + `llm_factory` → LangChain `init_chat_model`. Prefer `MAPPER_MODEL_ID=azure_openai:gpt-5-mini` or split `MAPPER_PROVIDER` / `MAPPER_MODEL`.

**Q: Did you use `init_chat_model`?**  
A: Yes — all built-in providers go through it; the factory still handles dual roles, Foundry endpoints, and custom `register_llm_provider`.

**Q: Streaming / human-in-the-loop?**  
A: Document Word pipeline is mostly batch. Voice → contract uses LangGraph `interrupt()` + `Command(resume=...)` with a `MemorySaver` thread id before generating files (see `voice_graph.py`).

**Q: Parallel nodes?**  
A: Not needed here (linear dependency). Would use fan-out if extract + enrich were independent.

---

## 9. Demo script (5 minutes)

1. Show `graph.py` — nodes, conditional retry.  
2. Show `DocumentProcessingState` — what travels between steps.  
3. Show `.env` — `MAPPER_PROVIDER=azure_openai`, `VALIDATOR_PROVIDER=groq`.  
4. Show `llm_factory.py` — `resolve_role_config` + builders.  
5. Optional: `agent.py` vs pipeline — same tools, different control.  
6. Run `scripts/check_llm_availability.py` — prove both providers live.

---

## 10. Cheat sheet — files to open in an interview

| File | Say this |
|------|----------|
| `graph.py` | “Here’s the LangGraph” |
| `models/state.py` | “Here’s the shared state” |
| `nodes/pipeline.py` | “Thin nodes → services” |
| `services/llm_factory.py` | “Dynamic dual LLM selection” |
| `agent.py` / `tools.py` | “Agent mode alternative” |
| `services/field_mapper.py` | “LLM #1 structured output” |
| `services/document_validator.py` | “LLM #2 critic” |

---

## 11. One-sentence close

> “LangGraph owns **control flow and retries**; LangChain models own **reasoning**; our factory owns **which model runs for which role** — so the graph stays stable while providers stay swappable.”
