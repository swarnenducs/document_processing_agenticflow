# Component cheat sheets

## `document-processing-mcp`

- **Owns:** document LangGraph, DOCX generation, mapper/validator prompts  
- **Exposes:** FastMCP `generate_document`  
- **Interview words:** extract → map → generate → validate → retry  

## `voice_enable_mcp`

- **Owns:** voice/contract LangGraph, STT integration points, HITL confirm  
- **Exposes:** `start_voice_contract`, `confirm_voice_contract`, `list_voice_contracts`  
- **Interview words:** interrupt, thread_id, human-in-the-loop  

## `central-agentic-flow` (MAF)

- **Owns:** NL agent + **all** MCP calls (`/ask` LLM, `/invoke` jobs)  
- **Exposes:** `POST /ask`, `POST /invoke`, `GET /tools`  
- **Add an MCP:** edit `central-agentic-flow/config/mcp_registry.yml` (or `MAF_EXTRA_MCPS=name=http://host:port/mcp`)  
- **Interview words:** orchestrator, MCP registry, tool prefixes  

## `ip_api`

- **Owns:** HTTP API, jobs, uploads, WebSockets, **MAF proxy only** (never MCP URLs)  
- **Exposes:** `/api/v1/*`, `/api/ask`  
- **Interview words:** gateway, xid, background jobs  

## `UI`

- **Owns:** Gradio UX  
- **Talks to:** API over HTTP (prefer); optional local fallbacks  
- **Interview words:** progress UX, HITL chat  

## Launcher / Compose

- `run_all_components.py` — local all-in-one  
- `docker-compose.yml` — containerized same topology  
