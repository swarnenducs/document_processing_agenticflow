# Flow understanding — system map

## Big picture

```text
User (Gradio UI :7860)
        │ HTTP
        ▼
   ip_api :8000  (FastAPI)
        │
        ├── /api/v1/documents/jobs   template + JSON `data` → Blob + SQL → MAF /invoke → Document MCP
        ├── /api/v1/voice/*          STT (optional) → MAF /invoke → Voice MCP
        ├── /api/v1/agents/*         thin proxies → MAF /invoke or /tools
        └── /api/ask  ─────────────► central-agentic-flow :8003 (MAF)
                                              │  only process that calls MCP
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
              document-processing-mcp :8001   voice :8002     extra MCP :8004+
```

## Docs in this folder

| File | Topic |
|---|---|
| [README.md](README.md) (this file) | End-to-end map |
| [function-by-function-debug.md](function-by-function-debug.md) | Function-by-function hops + debugger breakpoints |
| [azure-sql-blob.md](azure-sql-blob.md) | Azure SQL (SQLAlchemy) + Blob for document jobs |
| [adding-a-new-flow.md](adding-a-new-flow.md) | How to add a new flow across MCP / MAF / UI |
| [components-cheatsheet.md](components-cheatsheet.md) | Ports & ownership |

Related: [../maf-basic/06-tool-calling-and-hallucination.md](../maf-basic/06-tool-calling-and-hallucination.md) · [../maf-basic/07-azure-foundry-deploy-and-auth.md](../maf-basic/07-azure-foundry-deploy-and-auth.md)

## Document pipeline flow (LangGraph)

```text
START
  → load_data
  → extract_styles          # Word OOXML / styles / placeholders
  → map_fields              # LLM #1 mapper (JSON → template fields)
  → generate                # write styled .docx
  → validate                # LLM #2 critic
       │
       ├─ pass → finalize → END
       └─ fail + retries left → bump_retry → map_fields
```

**Interview line:** “LangGraph makes retry/routing explicit in the graph, not hidden in nested ifs.”

## Voice / contract flow (separate LangGraph)

```text
transcript / STT text
  → parse intent + entities
  → may PAUSE for human confirmation (HITL)
  → confirm → create/save contract
```

**Interview line:** “Voice has its own graph so document fill and conversational HITL don’t share one messy state.”

## MAF ask flow

```text
POST /api/ask { message }     # text only — no file upload
  → ip_api proxies to MAF :8003
  → MAF Agent (LLM + tool calling)
  → MCPStreamableHTTPTool → document_generate_document / voice_*
  → Document MCP (same generate_document as the job path)
  → natural language answer with tool results
```

MAF does **not** upload files. Jobs use `/invoke` (no LLM). Chat uses `/ask` (LLM picks tools). Extra MCPs: `central-agentic-flow/config/mcp_registry.yml` (optional `MAF_EXTRA_MCPS`).

**Interview line:** “MAF is the orchestrator; MCPs are the specialists. Separation of concerns.”

## Request correlation (xid)

Every HTTP request gets `X-Request-ID` (xid). Tools and LLM calls log with the same xid → you can rebuild a trace for debugging / interviews about observability.

## Data & prompts

| Concern | Where |
|---|---|
| Document prompts | `document-processing-mcp/prompts/*.yml` |
| Voice prompts | `voice_enable_mcp/prompts/` |
| MAF instructions | `central-agentic-flow/prompts/orchestrator_instructions.md` (preamble) + `config/mcp_registry.yml` (per-MCP) |
| Jobs / contracts | Azure SQL (`document_jobs`) + Azure Blob (template/JSON/output) when configured; else SQLite + local disk |

## Ports cheat sheet

| Service | Port |
|---|---|
| API | 8000 |
| Document MCP | 8001 |
| Voice MCP | 8002 |
| MAF | 8003 |
| UI | 7860 |
