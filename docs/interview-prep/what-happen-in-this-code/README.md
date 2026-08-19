# What happens in this code?

Step-by-step narratives you can speak in an interview while pointing at folders.

## 1) User uploads template + JSON (document job)

1. **UI** (`UI/`) POSTs files to **ip_api** `/api/v1/documents/...`
2. API saves blobs, creates **job** row (SQLite), returns `job_id`
3. Background runner starts document LangGraph (`document_processing_mcp.graph`)
4. Nodes run: load → extract styles → **mapper LLM** → generate DOCX → **validator LLM**
5. Stages published to in-process hub → UI **WebSocket** shows progress
6. Job status → completed; UI downloads output path / file

**Say:** “API owns jobs/UX; graph owns business pipeline.”

---

## 2) Natural language ask via MAF

1. Client `POST /api/ask` `{"message":"Generate doc using template X and data Y"}`
2. **ip_api** proxies to **central-agentic-flow** `:8003/ask`
3. MAF builds chat client from env; loads instructions from `prompts/orchestrator_instructions.md`
4. Connects `MCPStreamableHTTPTool` to `:8001` and `:8002`
5. Agent may call `document_generate_document` / voice tools
6. Returns summarized `text` (+ tool side effects already done)

**Say:** “Orchestrator chooses tools; specialists execute.”

---

## 3) Voice: “create contract with legal entity AVC ref CR 1001”

1. UI sends transcript (or Whisper STT → text) to API or MCP
2. **voice_enable_mcp** graph parses entities
3. If ambiguous → **HITL** needs confirmation (thread_id)
4. User confirms → `confirm_voice_contract` resumes graph
5. Contract saved (SQLite); response includes ids/paths

**Say:** “Separate voice graph + interrupt/resume for human confirmation.”

---

## 4) Direct MCP call (no MAF)

```bash
POST /api/v1/agents/document/generate
{ "template_path": "...", "data_path": "..." }
```

1. FastAPI MCP client opens HTTP session to `:8001/mcp`
2. Calls tool `generate_document`
3. Tool runs `invoke_document_graph(...)` inside MCP process
4. JSON result returned to client

**Say:** “Same graph whether invoked by API proxy or MAF.”

---

## 5) Mapper LLM call (inside document graph)

1. `map_fields` node → `field_mapper` service
2. Loads YAML prompt from `document-processing-mcp/prompts/mapper.yml`
3. `llm_factory.get_mapper_llm()` using `MAPPER_PROVIDER` / model
4. Structured mapping written into state
5. Confidence/scoring helpers annotate result

**Say:** “Prompts are config; providers are env; nodes stay thin.”

---

## 6) Validation retry loop

1. Validator scores output below threshold
2. Conditional edge → `bump_retry` if `retry_count < max_retries`
3. Back to `map_fields` with updated count
4. Else finalize or fail

**Say:** “Retry is a first-class graph concern.”

---

## 7) `run_all_components.py`

1. Starts MCP :8001, :8002
2. Starts MAF :8003
3. Starts API :8000
4. Starts UI :7860
5. Health-waits, then blocks until Ctrl+C

**Say:** “Local orchestration of independently deployable processes.”

---

## Files to open while explaining

| Story | Open |
|---|---|
| Document graph | `document-processing-mcp/.../graph.py` |
| Document MCP tool | `document-processing-mcp/.../server.py` |
| Voice graph | `voice_enable_mcp/.../graph.py` |
| MAF | `central-agentic-flow/.../orchestrator.py` |
| API ask proxy | `ip_api/.../api/ask_routes.py` |
| Job runner | `ip_api/.../services/pipeline_runner.py` |
