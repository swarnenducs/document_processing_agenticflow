# Adding a new flow (end-to-end)

How work moves through this repo today, and the checklist to add a **new** capability without breaking separation of concerns.

## How the overall flow works today

```text
┌────────────┐     HTTP      ┌──────────┐
│ Gradio UI  │ ────────────► │  ip_api  │  FastAPI gateway (:8000)
│  :7860     │               │          │  uploads, jobs SQL/Blob, STT
└────────────┘               └────┬─────┘
                                  │  ONLY talks to MAF
                                  ▼
                     central-agentic-flow (:8003)
                     MAF = LLM /ask  +  deterministic /invoke
                                  │
                   ┌──────────────┼──────────────┐
                   ▼              ▼              ▼
         document MCP :8001   voice MCP :8002   extra MCP :8004+
```

| Path | When to use |
|---|---|
| UI → `/api/v1/documents/jobs` | Fixed Generate Document screen. API stores Blob/SQL, then **MAF `/invoke`** → document MCP |
| UI → `/api/v1/voice/*` | Voice tab. API may STT, then **MAF `/invoke`** → voice MCP |
| UI → `/api/ask` (MAF) | Natural language; agent **chooses** which MCP tools to call |
| Direct MCP | Never from ip_api. Only MAF (or CLI/debug) calls MCP URLs |

**Rule:** business logic lives in the **MCP + its LangGraph**. MAF is the only orchestrator that calls MCP. `ip_api` is the HTTP edge (jobs, uploads, proxy).

## Layers you touch when adding something new

| Layer | Folder | Responsibility |
|---|---|---|
| 1. Domain graph | `document-processing-mcp` or `voice_enable_mcp` (or **new** MCP package) | Nodes, state, prompts, persistence |
| 2. MCP tools | that package’s `server.py` `register_tools()` | Typed tools the outside world can call |
| 3. Gateway (optional) | `ip_api/api/...` | REST for UI — must call MAF, never MCP URLs |
| 4. MAF registry | `central-agentic-flow/config/mcp_registry.yml` | URL, prefix, prompt, invoke modes (`ask` / `jobs`) |
| 5. UI (optional) | `UI/.../gradio_app.py` | Dedicated tab **or** rely on Central Agent tab |
| 6. Docs / health | interview-prep + `/api/v1/health` / `/agents/tools` | Discoverability |

## Checklist: add a new flow (recommended path)

### Option A — Extend an existing MCP (same domain)

Example: add `regenerate_document` next to `generate_document`.

1. **LangGraph / service** — implement the behavior in the MCP package (new node or function).
2. **Prompt** — add YAML/MD under that component’s `prompts/` (not the root).
3. **MCP tool** — `@self.tool` in `register_tools()` with a clear docstring (the LLM reads this).
4. **Gateway** — optional `POST /api/v1/...` that calls `invoke_tool("document", "regenerate_document", ...)`.
5. **MAF registry** — add the tool under that server’s `invoke.tools` in `central-agentic-flow/config/mcp_registry.yml` (`when` + request fields). The YAML prompt is what `/ask` sees.
6. **No orchestrator code change** if the MCP is already attached — MAF discovers live tools at runtime; YAML only adds invoke rules + when-to-call text.
7. **UI** — Refresh API status; new tool appears under **Available MCP tools**. Add a dedicated tab only if UX needs it.
8. **Smoke** — `GET /api/v1/agents/tools`, then `POST /api/ask` with a natural-language ask.

### Option B — New domain = new MCP service (preferred for a new product flow)

Example: “Fabric SQL agent” as its own deployable.

1. Copy the pattern of `document-processing-mcp/` (own `src/`, `prompts/`, `Dockerfile`, port e.g. `8004`).
2. Implement LangGraph + `register_tools()`.
3. Wire in `docker-compose.yml` / `run_all_components.py`.
4. Register on MAF in `central-agentic-flow/config/mcp_registry.yml` (copy the `fabric-sql-agent` example, set `enabled: true`)::

       - name: fabric-sql-agent
         enabled: true
         url: "${FABRIC_SQL_AGENT_URL:-http://127.0.0.1:8004/mcp}"
         prefix: fabric
         invoke:
           modes: [ask]          # LLM /ask only; add `jobs` for API /invoke
           default_tool: run_sql
           tools:
             run_sql:
               when: "User asks to query Fabric SQL / warehouse data."
         instructions: |
           Call fabric_run_sql with the SQL; never invent query results.

   One-off without editing YAML: `MAF_EXTRA_MCPS=fabric=http://127.0.0.1:8004/mcp`.
5. Shared preamble stays in `prompts/orchestrator_instructions.md`; per-MCP when/how is YAML.
6. Optional UI/API: REST that calls `invoke_tool("fabric", "...", ...)` — only if `jobs` is in `invoke.modes`.
7. Document the flow in `flow-understanding/`.

### Option C — Pure NL-only (no new UI tab)

Skip UI/API routes: only MCP + a YAML server with `invoke.modes: [ask]`. Users use **Central Agent (MAF)** tab.

## What not to do

- Do **not** put document/voice pipeline logic inside MAF — keep MAF thin.
- Do **not** call MCP URLs from `ip_api` — always MAF `/ask` or `/invoke`.
- Do **not** invent file paths / contract IDs in the LLM answer — tools must return them (see hallucination doc).
- Do **not** share one LangGraph for unrelated domains — separate graphs keep HITL/memory and retries clear.

## Quick verification

```bash
# Tools catalogue (UI uses this) — via MAF
curl -s http://127.0.0.1:8000/api/v1/agents/tools | jq

# MAF ask
curl -s http://127.0.0.1:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"message":"Call document_health and voice_health and summarize"}'
```

See also: [README.md](README.md) · [../maf-basic/06-tool-calling-and-hallucination.md](../maf-basic/06-tool-calling-and-hallucination.md)
