# Separate FastMCP servers: `document_process_mcp` + `voice_process_mcp`

Two **independent** FastMCP processes. FastAPI proxies to them over HTTP.

## Architecture

```text
Gradio UI ──► FastAPI (:8000)
                 │
                 ├── /api/v1/documents/*     (direct pipeline / jobs)
                 ├── /api/v1/voice/*         (direct voice workflow)
                 ├── /api/v1/agents/*        (proxies to FastMCP tools)
                 └── /api/ask ──► MAF (:8003) ──► MCP tools
                          │
          ┌───────────────┴────────────────┐
          ▼                                ▼
 document_process_mcp (:8001/mcp)   voice_process_mcp (:8002/mcp)
 DocumentProcessMCP                 VoiceProcessMCP
 (health, generate_document)        (health, start/confirm/list)
```

See [MAF_LOCAL.md](MAF_LOCAL.md) and [COMPONENTS.md](COMPONENTS.md).

## Run ALL components

```bash
python run_all_components.py
# or
uv run doc-all
# deprecated alias:
python run_both.py
```

Starts: FastAPI + Gradio + MAF + `document_process_mcp` + `voice_process_mcp`.

Useful flags:

```bash
python run_all_components.py --mcp-only
python run_all_components.py --maf-only
python run_all_components.py --api-only
python run_all_components.py --no-maf
python run_all_components.py --no-mcp
```

Standalone (separate processes, HTTP):

```bash
uv run document-process-mcp --transport http --port 8001
uv run voice-process-mcp --transport http --port 8002
uv run doc-maf   # :8003
uv run doc-api   # :8000
uv run doc-ui    # :7860
```

## FastAPI → MCP examples

```bash
curl -s http://127.0.0.1:8000/api/v1/agents/health

curl -s http://127.0.0.1:8000/api/v1/agents/document/generate \
  -H 'Content-Type: application/json' \
  -d '{"template_path":"samples/templates/complete_contract_template_GPO.docx","data_path":"samples/data/gpo_agreement.json"}'

curl -s http://127.0.0.1:8000/api/v1/agents/voice/contract \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"please create contract with legal entity AVC contract reference number CR 1001"}'
```

Env: `DOCUMENT_MCP_URL`, `VOICE_MCP_URL`, `MAF_BASE_URL` (see the matching `.env.example` in each component folder, or the repo-root `.env.example`).

Tool results are a **JSON object** (`result.data`), plus JSON-as-text for the LLM. See [FASTMCP_JSON.md](FASTMCP_JSON.md).
