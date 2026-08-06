# Separate FastMCP servers: `document_process_mcp` + `voice_process_mcp`

Two **independent** FastMCP processes. FastAPI proxies to them over HTTP.

## Architecture

```text
Gradio UI ──► FastAPI (:8000)
                 │
                 ├── /api/v1/documents/*     (direct pipeline / jobs)
                 ├── /api/v1/voice/*         (direct voice workflow)
                 └── /api/v1/agents/*        (proxies to FastMCP tools)
                          │
          ┌───────────────┴────────────────┐
          ▼                                ▼
 document_process_mcp (:8001/mcp)   voice_process_mcp (:8002/mcp)
 DocumentProcessMCP                 VoiceProcessMCP
 (health, generate_document)        (health, start/confirm/list)
```

## Modules

- [`mcp/base.py`](src/document_processing_agenticflow/mcp/base.py) — `BaseAgentMCPServer(FastMCP)`
- [`mcp/document_process_mcp.py`](src/document_processing_agenticflow/mcp/document_process_mcp.py) — **`document_process_mcp`**
- [`mcp/voice_process_mcp.py`](src/document_processing_agenticflow/mcp/voice_process_mcp.py) — **`voice_process_mcp`**
- [`mcp/client.py`](src/document_processing_agenticflow/mcp/client.py) — FastAPI client helper

## Run ALL services

```bash
python run_both.py
# or
uv run doc-app
```

Starts: FastAPI + Gradio + `document_process_mcp` + `voice_process_mcp`.

Useful flags:

```bash
python run_both.py --mcp-only                 # only MCP agents (HTTP)
python run_both.py --mcp-only --mcp-http      # explicit HTTP mode
python run_both.py --mcp-transport http       # same; default for run_both
python run_both.py --no-mcp                   # API + UI only
python run_both.py --api-only
```

Standalone (separate processes, HTTP):

```bash
uv run document-process-mcp --transport http --port 8001
uv run voice-process-mcp --transport http --port 8002
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

Env: `DOCUMENT_MCP_URL`, `VOICE_MCP_URL` (see `.env.example`).
