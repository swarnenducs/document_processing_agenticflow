# Interview Prep — GenAI / Agentic Systems

Notes mapped to **this repo** so you can explain architecture, code, and trade-offs in a GenAI interview.

## How to use (1–2 day plan)

| Time | Study |
|---|---|
| 30 min | [00-elevator-pitch.md](00-elevator-pitch.md) + [flow-understanding/](flow-understanding/) |
| 1–2 h | [fastapi-basic/](fastapi-basic/) → [langchain-basic/](langchain-basic/) (incl. RAG) → **[langgraph-basic/](langgraph-basic/)** (incl. **memory / HITL**) |
| 1–1.5 h | **[maf-basic/](maf-basic/)** (incl. tool calling / hallucination + **Foundry deploy**) + [mcp-basic/](mcp-basic/) |
| 1–2 h | [what-happen-in-this-code/](what-happen-in-this-code/) (walk the real paths) |
| 1 h | [qa-bank/](qa-bank/) — speak answers out loud |
| ongoing | [Course_link.md](Course_link.md) — YouTube / Udemy / Coursera / Microsoft certs |
| 15 min | [resume-bullets.md](resume-bullets.md) — project lines for resume / LinkedIn |

## Folder map

```text
docs/interview-prep/
  00-elevator-pitch.md
  Course_link.md           # YouTube + Udemy + Coursera + Microsoft cert tables
  resume-bullets.md        # Resume / LinkedIn bullets for this project
  fastapi-basic/           # API gateway, async, jobs, WebSockets
  langchain-basic/         # core LCEL + RAG (full) + agents + repo mapping + Q&A
  langgraph-basic/         # graphs + HITL + SQL checkpointer + memory types
  maf-basic/               # MAF agent+MCP code + sessions/memory
  mcp-basic/               # Model Context Protocol + FastMCP
  memory/                  # → see langgraph-basic/04-memory-management.md (canonical)
  flow-understanding/      # end-to-end system flows + function-by-function debug
  what-happen-in-this-code/# request → code path narratives
  qa-bank/                 # likely interview Q&A
```

## Components you must name in interviews

| Component | Port | One-line |
|---|---|---|
| `UI` | 7860 | Gradio client |
| `ip_api` | 8000 | FastAPI gateway / jobs / proxies |
| `document-processing-mcp` | 8001 | Document LangGraph as MCP tools |
| `voice_enable_mcp` | 8002 | Voice/contract LangGraph as MCP tools |
| `central-agentic-flow` | 8003 | MAF NL orchestrator → MCP tools |

Start everything: `python run_all_components.py`
