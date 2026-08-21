# 03 — MAF architecture in this repo

```text
Client
  │
  ├─ POST /api/ask ──► ip_api :8000 ──proxy──► central-agentic-flow :8003
  │                                              │
  │                                              ├─ MCP HTTP ► document :8001
  │                                              └─ MCP HTTP ► voice :8002
  │
  └─ POST /api/v1/agents/* ──► ip_api ──► same MCPs (no MAF)
```

## Separation of concerns

| Layer | Owns |
|---|---|
| MAF | NL understanding, tool selection, answer synthesis |
| Document MCP | Word pipeline LangGraph |
| Voice MCP | Voice/HITL LangGraph + SQLAlchemy checkpointer |
| ip_api | Jobs, auth edge, proxies, WebSockets |
| UI | UX |

**Interview line:** “MAF is the conductor; LangGraphs are the musicians.”

## Env cheat sheet

| Var | Meaning |
|---|---|
| `MAF_BASE_URL` | Service URL (`http://127.0.0.1:8003`) |
| `MAF_PROVIDER` / `MAF_MODEL` | Orchestrator LLM |
| `MAF_LLM_BASE_URL` | Optional LLM endpoint override |
| `DOCUMENT_MCP_URL` / `VOICE_MCP_URL` | Tool servers |
| `MAF_PROMPTS_DIR` | Instructions folder |

Prompts: `central-agentic-flow/prompts/orchestrator_instructions.md`

Next: [04-memory-and-sessions.md](04-memory-and-sessions.md)
