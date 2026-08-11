# Adding a new flow (end-to-end)

How work moves through this repo today, and the checklist to add a **new** capability without breaking separation of concerns.

## How the overall flow works today

```text
┌────────────┐     HTTP      ┌──────────┐
│ Gradio UI  │ ────────────► │  ip_api  │  FastAPI gateway (:8000)
│  :7860     │               └────┬─────┘
└────────────┘                    │
          ┌───────────────────────┼───────────────────────────┐
          │                       │                           │
          ▼                       ▼                           ▼
   /api/v1/documents/*     /api/v1/voice/*              /api/ask
   (direct jobs)           (HITL contract)                   │
          │                       │                           ▼
          │                       │              central-agentic-flow (:8003)
          │                       │              MAF Agent = LLM + tool calling
          │                       │                           │
          │                       │            ┌──────────────┴──────────────┐
          ▼                       ▼            ▼                             ▼
 document-processing-mcp (:8001)          voice_enable_mcp (:8002)
 LangGraph: extract→map→gen→validate      LangGraph: start → HITL → confirm
 MCP tools: health, generate_document     MCP tools: health, start_*, confirm_*, list_*
```

| Path | When to use |
|---|---|
| UI → `/api/v1/...` | Fixed screens (Generate Document, Voice chat) that know exact APIs |
| UI → `/api/ask` (MAF) | Natural language; agent **chooses** which MCP tools to call |
| Direct MCP | Other agents / CLI / Foundry-hosted agent pointing at MCP URLs |

**Rule of thumb:** business logic lives in the **MCP + its LangGraph**. MAF only plans and calls tools. `ip_api` is the HTTP edge (jobs, proxy, health).

## Layers you touch when adding something new

| Layer | Folder | Responsibility |
|---|---|---|
| 1. Domain graph | `document-processing-mcp` or `voice_enable_mcp` (or **new** MCP package) | Nodes, state, prompts, persistence |
| 2. MCP tools | that package’s `server.py` `register_tools()` | Typed tools the outside world can call |
| 3. Gateway (optional) | `ip_api/api/...` | REST for UI / integrations that skip MAF |
| 4. MAF wiring | `central-agentic-flow/.../orchestrator.py` | Attach MCP URL + prefix; update instructions |
| 5. UI (optional) | `UI/.../gradio_app.py` | Dedicated tab **or** rely on Central Agent tab |
| 6. Docs / health | interview-prep + `/api/v1/health` / `/agents/tools` | Discoverability |

## Checklist: add a new flow (recommended path)

### Option A — Extend an existing MCP (same domain)

Example: add `regenerate_document` next to `generate_document`.

1. **LangGraph / service** — implement the behavior in the MCP package (new node or function).
2. **Prompt** — add YAML/MD under that component’s `prompts/` (not the root).
3. **MCP tool** — `@self.tool` in `register_tools()` with a clear docstring (the LLM reads this).
4. **Gateway** — optional `POST /api/v1/...` if UI needs a fixed button.
5. **MAF instructions** — update `central-agentic-flow/prompts/orchestrator_instructions.md` so the agent knows when to call the new tool.
6. **No orchestrator code change** if the MCP is already attached — MAF discovers tools at runtime via MCP.
7. **UI** — Refresh API status; new tool appears under **Available MCP tools**. Add a dedicated tab only if UX needs it.
8. **Smoke** — `GET /api/v1/agents/tools`, then `POST /api/ask` with a natural-language ask.

### Option B — New domain = new MCP service (preferred for a new product flow)

Example: “invoice matching” as its own deployable.

1. Copy the pattern of `document-processing-mcp/` (own `src/`, `prompts/`, `Dockerfile`, port e.g. `8004`).
2. Implement LangGraph + `register_tools()`.
3. Wire in `docker-compose.yml` / `run_all_components.py`.
4. In `orchestrator.py`, add another `MCPStreamableHTTPTool(...)` with a **unique** `tool_name_prefix` (e.g. `invoice`).
5. Set `INVOICE_MCP_URL` (and health probe in `ip_api` `/api/v1/health` + `/agents/tools`).
6. Update MAF instructions with when to use invoice tools.
7. Document the flow in `flow-understanding/`.

### Option C — Pure NL-only (no new UI tab)

Skip UI/API routes: only MCP + MAF instructions. Users use **Central Agent (MAF)** tab.

## What not to do

- Do **not** put document/voice pipeline logic inside MAF — keep MAF thin.
- Do **not** invent file paths / contract IDs in the LLM answer — tools must return them (see hallucination doc).
- Do **not** share one LangGraph for unrelated domains — separate graphs keep HITL/memory and retries clear.

## Quick verification

```bash
# Tools catalogue (UI uses this)
curl -s http://127.0.0.1:8000/api/v1/agents/tools | jq

# MAF ask
curl -s http://127.0.0.1:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"message":"Call document_health and voice_health and summarize"}'
```

See also: [README.md](README.md) · [../maf-basic/06-tool-calling-and-hallucination.md](../maf-basic/06-tool-calling-and-hallucination.md)
