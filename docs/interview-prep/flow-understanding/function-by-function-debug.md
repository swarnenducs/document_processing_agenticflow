# Function-by-function flow + debugging

This is the walkthrough for **this repo**: every hop is a real function. Use it with the Cursor/VS Code debugger.

Related: [README.md](README.md) (architecture) · [adding-a-new-flow.md](adding-a-new-flow.md)

---

## How to debug (pick one)

### A — Red-dot breakpoints (recommended)

1. Open **Run and Debug**.
2. Start **`Debug: all services`** (or one service if you already have the others running).
3. Click the gutter on any function listed below. Trigger the UI / curl. Execution stops there.

Do **not** also run `python run_all_components.py` on the same ports.

### B — Flow logger (`file + method`, default off)

Prints `file:line method` as your code runs. Normal `python run_all_components.py` does nothing.

```bash
# Every project function/method (UI, API, MAF, both MCPs)
export DEBUG_FLOW=1

# Only the named hops already wired in code
export DEBUG_FLOW=hops

# Restrict either mode to selected names
export DEBUG_FLOW_POINTS=create_document_job,map_fields_node,ask_maf

# Also pause in the debugger at matching hops (need F5)
export DEBUG_FLOW_BREAK=1
```

Restart the services after changing env. Lines look like:

```text
[FLOW] enabled mode=trace (file + method)
[FLOW]   ip_api/src/ip_api/api/routes.py:331 create_document_job  [create_document_job]
[FLOW]     ip_api/src/ip_api/services/pipeline_runner.py:18 run_document_job
```

Helper: [`flow_debug.py`](../../flow_debug.py) at repo root (same module in each package).

---

## Watch these locals

| Variable | Meaning |
|---|---|
| `xid` | Request correlation id (`X-Request-ID`) |
| `session_id` | UI/API session (SQLite in `ip_api`) |
| `job_id` | Document job row |
| `thread_id` | Voice LangGraph HITL checkpointer key |
| `state` / `snapshot` | LangGraph document/voice state |
| `mapping` / `validation` / `confidence` | Document pipeline artifacts |

---

## Flow 1 — Generate document (UI button → LangGraph → .docx)

This is the **fixed UI path**. The API uploads files to Blob (when configured), stores blob refs in SQL, and calls Document MCP `:8001`. MCP downloads, runs LangGraph, uploads the output, and completes the SQL row.

```text
ui_generate_document
  → create_document_job (HTTP POST /api/v1/documents/jobs)
      → insert_job (blob refs in document_jobs)
      → run_document_job (FastAPI BackgroundTasks)
          → MAF /invoke document generate_document
              → download blobs
              → invoke_document_graph
                  → load_data_node
                  → extract_styles_node
                  → validate_extraction_node
                  → map_fields_node          # LLM mapper
                  → generate_document_node
                  → validate_document_node   # LLM critic; may retry
                  → [_bump_retry → map_fields_node]  # optional
                  → finalize_node
              → upload output .docx + complete SQL
      → GET job status / WebSocket stages
      → download
```

| # | Function | File | `DEBUG_FLOW_POINTS` | Inspect |
|---|---|---|---|---|
| 1 | `ui_generate_document` | `UI/src/ui_app/ui/gradio_app.py` | `ui_generate_document` | uploaded template, JSON, `session_id` |
| 2 | `create_document_job` | `UI/.../api_client.py` | *(HTTP client)* | multipart files |
| 3 | `create_document_job` | `ip_api/.../api/routes.py` | `create_document_job` | saved paths, `job_id`, `xid` |
| 4 | `run_document_job` | `ip_api/.../pipeline_runner.py` | `run_document_job` | blob refs + MCP call |
| 5 | `generate_document` | `document-processing-mcp/.../server.py` | `mcp_generate_document` | blob refs, `job_id` |
| 6 | `run_generate_document` | `.../services/document_job.py` | *(download/upload)* | local scratch paths |
| 7 | `stream_document_graph` | `document-processing-mcp/.../graph.py` | `stream_document_graph` | initial state dict |
| 8 | `load_data_node` | `.../nodes/pipeline.py` | `load_data_node` | `json_data` |
| 9 | `extract_styles_node` | same | `extract_styles_node` | `extracted` placeholders |
| 10 | `validate_extraction_node` | same | `validate_extraction_node` | extraction critic |
| 11 | `map_fields_node` | same | `map_fields_node` | `mapping` (LLM #1) |
| 12 | `generate_document_node` | same | `generate_document_node` | `generation.output_path` |
| 13 | `validate_document_node` | same | `validate_document_node` | `validation.passed`, score |
| 14 | `_after_validation` / `_bump_retry` | `.../graph.py` | *(red-dot)* | retry vs finalize |
| 15 | `finalize_node` | `.../nodes/pipeline.py` | `finalize_node` | `confidence` |
| 16 | `publish_job_stage` | `ip_api/.../job_events.py` | *(red-dot)* | WebSocket stage name |

Suggested first walk: `DEBUG_FLOW_POINTS=create_document_job,map_fields_node,validate_document_node,finalize_node`

---

## Flow 2 — Same pipeline via MCP (MAF or `/api/v1/agents/document/generate`)

Business logic is the **same graph**. Entry is the MCP tool, not the job runner.

```text
[UI Central Agent] ui_central_agent_ask
  → ask_central_agent  POST /api/ask
      → ask  (ip_api ask_routes)
          → POST :8003/ask  maf_http_ask
              → ask_maf
                  → Agent.run  → MCP tool document_generate_document
                      → generate_document (MCP server)
                          → invoke_document_graph → same nodes as Flow 1
```

Direct API (skip MAF):

```text
document_generate_via_mcp  POST /api/v1/agents/document/generate
  → MCPAgentClient.call_tool("generate_document")
      → generate_document (MCP :8001)
```

| # | Function | File | `DEBUG_FLOW_POINTS` | Inspect |
|---|---|---|---|---|
| 1 | `ui_central_agent_ask` | `UI/.../gradio_app.py` | `ui_central_agent_ask` | user `message` |
| 2 | `ask_central_agent` | `UI/.../api_client.py` | *(HTTP)* | JSON body |
| 3 | `ask` | `ip_api/.../ask_routes.py` | `api_ask` | session, proxy URL |
| 4 | `ask` | `central-agentic-flow/.../server.py` | `maf_http_ask` | `body.message` |
| 5 | `ask_maf` | `central-agentic-flow/.../orchestrator.py` | `ask_maf` | MCP URLs, agent tools |
| 6 | `call_tool` | `ip_api/.../mcp_client.py` | `mcp_call_tool` | tool `name`, args (gateway path only) |
| 7 | `document_generate_via_mcp` | `ip_api/.../mcp_routes.py` | `document_generate_via_mcp` | paths |
| 8 | `generate_document` | `document-processing-mcp/.../server.py` | `mcp_generate_document` | template/data paths |
| 9 | nodes | same as Flow 1 | same names | graph state |

MAF talks to MCP **directly** (not through `ip_api.mcp_client`). To debug tool execution, put breakpoints in the **Document MCP** process.

---

## Flow 3 — Voice create-contract + HITL

UI/API path (graph in-process via `voice_enable_mcp`):

```text
ui_contract_chat / ui_contract_chat_from_audio
  → voice_contract_from_text  POST /api/v1/voice/contract
      → run_voice_contract_workflow
          → start_voice_contract_agent
              → parse_intent_node
              → fetch_legal_entity_node
              → fetch_pricelist_node
              → await_confirmation_node   # interrupt()  → status=needs_confirmation
  → user says yes
  → voice_contract_confirm  POST /api/v1/voice/contract/confirm
      → confirm_voice_contract
          → resume_voice_contract_agent(Command(resume=...))
              → generate_contract_node
```

MCP/MAF path: `start_voice_contract` / `confirm_voice_contract` in `voice_enable_mcp/.../server.py`.

| # | Function | File | `DEBUG_FLOW_POINTS` | Inspect |
|---|---|---|---|---|
| 1 | `voice_contract_from_text` | `ip_api/.../routes.py` | `voice_contract_from_text` | `transcript` |
| 2 | `start_voice_contract_agent` | `voice_enable_mcp/.../graph.py` | `start_voice_contract_agent` | `thread_id` |
| 3 | `parse_intent_node` | `.../nodes/voice_contract.py` | `parse_intent_node` | entity + ref |
| 4 | `await_confirmation_node` | same | `await_confirmation_node` | `interrupt` payload |
| 5 | `voice_contract_confirm` | `ip_api/.../routes.py` | `voice_contract_confirm` | `thread_id`, ref |
| 6 | `resume_voice_contract_agent` | `.../graph.py` | `resume_voice_contract_agent` | resume payload |
| 7 | `generate_contract_node` | `.../nodes/voice_contract.py` | `generate_contract_node` | output files |
| 8 | `start_voice_contract` (tool) | `voice_enable_mcp/.../server.py` | `mcp_start_voice_contract` | MCP entry |
| 9 | `confirm_voice_contract` (tool) | same | `mcp_confirm_voice_contract` | MCP resume |

HITL resumes from SQL (`lg_checkpoints`) using `thread_id`. Restarting Voice MCP does **not** drop a pending confirmation as long as SQLite / Azure SQL is intact.

---

## Named points (copy-paste)

```text
ui_generate_document,ui_central_agent_ask,
create_document_job,run_document_job,stream_document_graph,
load_data_node,extract_styles_node,validate_extraction_node,
map_fields_node,generate_document_node,validate_document_node,finalize_node,
mcp_generate_document,document_generate_via_mcp,mcp_call_tool,
api_ask,maf_http_ask,ask_maf,
voice_contract_from_text,voice_contract_confirm,
start_voice_contract_agent,parse_intent_node,await_confirmation_node,
resume_voice_contract_agent,generate_contract_node,
mcp_start_voice_contract,mcp_confirm_voice_contract
```

---

## Which process owns which breakpoint?

| You clicked a breakpoint in… | Start this debug config |
|---|---|
| `UI/src/...` | Debug: UI Gradio |
| `ip_api/src/...` | Debug: API |
| `document-processing-mcp/...` (MCP tool path) | Debug: Document MCP |
| `document-processing-mcp/...` (UI Generate Document button) | Debug: Document MCP (API only forwards blob refs) |
| `voice_enable_mcp/...` (Voice tab) | Debug: API |
| `voice_enable_mcp/...` (MAF tool) | Debug: Voice MCP |
| `central-agentic-flow/...` | Debug: MAF |

---

## Quick curl triggers

```bash
# Document job (Flow 1) — use your template + JSON from the Gradio tab, or:
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/jobs \
  -F "template=@/path/to/template.docx" \
  -F "data=<samples/data/gpo_agreement.json"

# MAF (Flow 2)
curl -s -X POST http://127.0.0.1:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"message":"List available MCP tools and say hello"}'

# Voice start (Flow 3)
curl -s -X POST http://127.0.0.1:8000/api/v1/voice/contract \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"create contract for legal entity AVC reference CR 1001"}'
```

Sample filenames may differ in your tree; if curl 400s, use the Gradio tabs instead.
