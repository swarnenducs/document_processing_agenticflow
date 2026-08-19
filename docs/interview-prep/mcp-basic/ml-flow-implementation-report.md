# MLflow implementation report

**Scope:** Basic plan only — what to change to add MLflow GenAI tracing to this stack.  
**Status:** Not implemented yet (design / change list).  
**Date:** 2026-08-11

---

## 1. Goal

Monitor **multiple LLMs and MCP tool calls** in one place:

| Signal | Source today |
|---|---|
| MAF orchestrator LLM | `central-agentic-flow` |
| Mapper LLM #1 | `document-processing-mcp` |
| Validator LLM #2 | `document-processing-mcp` |
| Voice / contract LLM (if any) | `voice_enable_mcp` |
| MCP tool invoke | MCP servers + `ip_api` client |
| Correlation | existing `xid` |

MLflow **adds observability**; it does **not** replace FastMCP, LangGraph, or SQLite `xid` traces (can run in parallel).

---

## 2. Recommended architecture

```text
                    ┌─────────────────────┐
                    │  MLflow Tracking UI │  :5000
                    │  (traces / experiments)
                    └──────────▲──────────┘
                               │ HTTP (MLFLOW_TRACKING_URI)
     ┌─────────────────────────┼─────────────────────────┐
     │                         │                         │
 document-mcp            voice-mcp                 central-agentic-flow
 (mapper/validator)      (tool spans / LLM)        (MAF + tool loop)
     │                         │                         │
     └─────────────────────────┴─────────────────────────┘
                               │
                            ip_api
                     (optional: gateway spans)
```

**Local first:** one MLflow server (Docker or `mlflow ui`).  
**Later:** Azure Blob / Databricks / managed MLflow as tracking backend.

---

## 3. Changes required (by layer)

### 3.1 Infrastructure (new)

| Change | Detail |
|---|---|
| Add MLflow service | Docker Compose service `mlflow` on port `5000` (or run `mlflow server` locally) |
| Persist artifacts | Volume for `./data/mlflow` (or remote store) |
| Env vars | `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME`, `MLFLOW_ENABLED=true/false` |
| Optional | `mlflow-tracing` package in prod images (smaller footprint) |

**Compose sketch**

```yaml
# docker-compose.yml (add)
mlflow:
  image: ghcr.io/mlflow/mlflow:v2.20.0   # pin a version you verify
  ports: ["5000:5000"]
  command: mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db
  volumes: ["./data/mlflow:/mlflow"]
```

Wire `MLFLOW_TRACKING_URI=http://mlflow:5000` into MCP / MAF / API containers.

### 3.2 Dependencies

| Package | Where |
|---|---|
| `mlflow` (dev) or `mlflow-tracing` (prod) | `document-processing-mcp`, `voice_enable_mcp`, `central-agentic-flow`, optionally `ip_api` |
| Keep existing LangChain / OpenAI clients | No swap required for Phase 1 |

### 3.3 Shared bootstrap (small new module per component or one copy)

Add something like `observability/mlflow_setup.py` in each self-contained component (same pattern as duplicated `llm_factory`):

```python
# Pseudocode — enable once at process start
def init_mlflow():
    if os.getenv("MLFLOW_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return
    import mlflow
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT_NAME", "document-agentic-flow"))
    # Autolog where supported:
    try:
        mlflow.langchain.autolog()
    except Exception:
        pass
    try:
        mlflow.openai.autolog()
    except Exception:
        pass
```

Call `init_mlflow()` from each component’s `main` / server entrypoint.

### 3.4 Document MCP — required code touch points

| File / area | Change |
|---|---|
| `document_processing_mcp` entry (`server.py` / `__main__`) | Call `init_mlflow()` |
| `services/field_mapper.py` | Ensure mapper LLM calls are under LangChain/OpenAI autolog **or** wrap `traced_invoke` with `@mlflow.trace(span_type="LLM")` |
| `services/document_validator.py` | Same for validator |
| `server.py` tools (`generate_document`, `health`) | `@mlflow.trace(name="mcp.generate_document", span_type="TOOL")` on tool bodies |
| Graph invoke | Optional parent span `document_graph` around `invoke_document_graph` |
| Tags | Set `xid`, `component=document_mcp`, `model=<mapper/validator id>` on spans |

### 3.5 Voice MCP — required code touch points

| File / area | Change |
|---|---|
| Voice server entry | `init_mlflow()` |
| `start_voice_contract` / `confirm_voice_contract` tools | Tool-level `@mlflow.trace` |
| LLM / STT paths in `llm_factory` / speech | Autolog or manual spans; tag `component=voice_mcp` |
| HITL resume | Same `thread_id` / `xid` as span attributes |

### 3.6 Central agentic flow (MAF) — required code touch points

| File / area | Change |
|---|---|
| `server.py` / CLI entry | `init_mlflow()` |
| `orchestrator.ask_maf` | Parent span `maf.ask`; nested spans for agent run |
| Chat client | Prefer OpenAI autolog if using OpenAI-compatible SDK; else manual span around `agent.run` |
| Tags | `component=maf`, `model=MAF_MODEL`, `xid` if propagated |

**Note:** Agent Framework may not have first-class MLflow autolog — **manual parent span + tool child spans** is the safe Phase 1 approach.

### 3.7 ip_api (optional but useful)

| File / area | Change |
|---|---|
| App startup | `init_mlflow()` if gateway tracing desired |
| `mcp_client.call_tool` | Span `gateway.mcp_tool` with tool name + latency |
| `/api/ask` proxy | Span `gateway.ask` linking to MAF (propagate trace context if possible) |

### 3.8 UI

| Change | Need? |
|---|---|
| Gradio changes | **No** for Phase 1 |
| Optional later | Link “open MLflow” in health panel |

### 3.9 Config / docs

| Change | Detail |
|---|---|
| `.env.example` | `MLFLOW_ENABLED`, `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME` |
| `run_all_components.py` / compose | Start MLflow when enabled |
| Interview / ops doc | Point to this report + UI URL `http://127.0.0.1:5000` |

### 3.10 Tests

| Change | Detail |
|---|---|
| Unit tests | Keep `MLFLOW_ENABLED=false` by default so CI stays offline |
| Optional smoke | One test that records a fake span to a temp tracking URI |

---

## 4. Phased rollout

| Phase | Deliverable | Effort (rough) |
|---|---|---|
| **P0** | MLflow server + env flags; no app code | 0.5 day |
| **P1** | `init_mlflow` + autolog in document MCP (mapper/validator) | 0.5–1 day |
| **P2** | Manual tool spans on both MCPs + tag `xid` | 0.5 day |
| **P3** | MAF `ask_maf` parent span | 0.5 day |
| **P4** | Gateway spans + compose wiring for all services | 0.5 day |
| **P5** (later) | Evaluations / judges on traces; remote backend | 1–2 days |

**Minimum useful slice:** P0 + P1 + P2 → you can already compare mapper vs validator vs tool latency in the MLflow UI.

---

## 5. What we do *not* need to change

| Keep as-is | Reason |
|---|---|
| FastMCP tool contracts | Observability is additive |
| LangGraph graph topology | Autolog / wraps around invokes |
| MAF ↔ MCP architecture | Still the tool bus |
| Existing SQLite `xid` / Trace Logs UI | Complementary ops view |
| Gradio feature set | Optional later |

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Extra latency / deps in hot path | Feature flag; async/production tracing SDK; sample rate |
| PII in prompts logged to MLflow | Redact; disable in prod or use sampling |
| Autolog misses Agent Framework / FastMCP | Manual `@mlflow.trace` (expected) |
| Duplicated `llm_factory` across packages | Copy small `mlflow_setup` into each component (same as current style) |

---

## 7. Success criteria

1. With `MLFLOW_ENABLED=true`, a document job creates visible spans for **mapper**, **validator**, and **`generate_document`**.
2. An `/api/ask` creates a **maf.ask** span (with or without nested tool spans).
3. Spans carry **`xid`** so they can be joined with existing Trace Logs.
4. With flag **off**, behavior and CI are unchanged.

---

## 8. One-line summary

**Add an MLflow tracking server + a small `init_mlflow()` bootstrap in each LLM/MCP process, wrap MCP tools (and MAF `ask`) with traces, tag by component/`xid`/model — no redesign of FastMCP or LangGraph required.**
