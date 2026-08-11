# Flow understanding — system map

## Big picture

```text
User (Gradio UI :7860)
        │ HTTP
        ▼
   ip_api :8000  (FastAPI)
        │
        ├── /api/v1/documents/*     jobs + pipeline (document graph)
        ├── /api/v1/voice/*         voice workflow
        ├── /api/v1/agents/*        thin proxies → MCP tools
        └── /api/ask  ─────────────► central-agentic-flow :8003 (MAF)
                                              │
                         ┌────────────────────┴────────────────────┐
                         ▼                                         ▼
              document-processing-mcp :8001            voice_enable_mcp :8002
              (document LangGraph)                     (voice LangGraph)
```

## Docs in this folder

| File | Topic |
|---|---|
| [README.md](README.md) (this file) | End-to-end map |
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
POST /api/ask { message }
  → ip_api proxies to MAF :8003
  → MAF Agent (LLM + tool calling)
  → MCPStreamableHTTPTool → document_* and voice_* tools
  → natural language answer with tool results
```

**Interview line:** “MAF is the orchestrator; MCPs are the specialists. Separation of concerns.”

## Request correlation (xid)

Every HTTP request gets `X-Request-ID` (xid). Tools and LLM calls log with the same xid → you can rebuild a trace for debugging / interviews about observability.

## Data & prompts

| Concern | Where |
|---|---|
| Document prompts | `document-processing-mcp/prompts/*.yml` |
| Voice prompts | `voice_enable_mcp/prompts/` |
| MAF instructions | `central-agentic-flow/prompts/orchestrator_instructions.md` |
| Jobs / contracts | SQLite + filesystem storage (configurable paths) |

## Ports cheat sheet

| Service | Port |
|---|---|
| API | 8000 |
| Document MCP | 8001 |
| Voice MCP | 8002 |
| MAF | 8003 |
| UI | 7860 |
