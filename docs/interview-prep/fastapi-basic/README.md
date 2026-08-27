# FastAPI basics (for this project)

## Why FastAPI here?

- Async HTTP for uploads + long jobs
- OpenAPI docs for demos (`/docs`)
- WebSockets for job progress
- Thin gateway in front of MCP / MAF

**Component:** `ipp_agentic_api/` → `uv run doc-api` → `:8000`

## Concepts you must explain

### 1. App factory + lifespan

```python
# pattern
def create_app() -> FastAPI:
    app = FastAPI(...)
    app.include_router(...)
    return app
```

Lifespan loads `.env`, ensures storage dirs. Interview: “startup/shutdown hooks without global side effects in import time.”

### 2. Routers & prefixes

| Prefix | Role |
|---|---|
| `/api/v1/...` | documents, voice, agent proxies |
| `/api/ask` | MAF proxy (intentionally not under v1) |

### 3. Pydantic models

Request/response schemas = contract with clients. Interview: “validation at the edge; keep domain logic out of route handlers when possible.”

### 4. Background jobs

Pattern in this repo:

1. Accept upload → create job row (SQLite)
2. Return `job_id` quickly
3. Run LangGraph in background / worker
4. Client polls or **WebSocket** for stages

**Why not block HTTP?** Document generation can take minutes (LLM + DOCX).

### 5. Middleware (xid)

`XidMiddleware` attaches correlation id to every request and logs latency.  
Talking point: “distributed tracing lite without full OpenTelemetry.”

### 6. WebSockets

`WS /api/v1/documents/jobs/{id}/ws` — in-process event hub publishes stages (`styles_extracted`, `fields_mapped`, …).  
Interview: “pub/sub in-process is fine for single replica; Redis if multi-instance.”

### 7. Proxy routes

`/api/v1/agents/*` → FastMCP HTTP tools  
`/api/ask` → MAF `:8003`

API can stay thin: auth, uploads, status, orchestration entry — heavy work in MCP.

## Common interview Qs

**Q: FastAPI vs Flask?**  
A: Native async, type hints + Pydantic, auto OpenAPI, first-class WebSockets.

**Q: Sync LLM call inside async route?**  
A: Prefer `asyncio.to_thread` / background task / separate worker so event loop isn’t blocked.

**Q: How do you version APIs?**  
A: `/api/v1` prefix; keep `/api/ask` as product surface for NL orchestration.

## Point to code

- `ipp_agentic_api/src/ip_api/api/main.py` — app + xid middleware
- `ipp_agentic_api/src/ip_api/api/routes.py` — documents/jobs
- `ipp_agentic_api/src/ip_api/api/ask_routes.py` — MAF proxy
- `ipp_agentic_api/src/ip_api/api/mcp_routes.py` — MCP proxy
