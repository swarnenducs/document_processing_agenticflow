# FastMCP in this project — validity, examples, `/docs`, MLflow

## Verdict: is our FastMCP use case valid?

**Yes — valid and aligned with how FastMCP / MCP are meant to be used.**

We expose **specialist capabilities as MCP tools over HTTP**, then let **multiple hosts** (FastAPI gateway, MAF agent, future Foundry agents) call the same tools. That is the core MCP value proposition.

### Validation table (our design vs FastMCP best practice)

| # | Our use case | FastMCP / MCP fit? | Why it is valid |
|---|---|---|---|
| 1 | Separate processes: `document_process_mcp` (:8001) + `voice_process_mcp` (:8002) | **Valid** | One server per domain; independently deployable |
| 2 | HTTP streamable transport (`/mcp`) for microservices | **Valid** | FastMCP first-class `transport="http"` for remote clients |
| 3 | Tools wrap LangGraph pipelines (`generate_document`, voice HITL) | **Valid** | Tools are the public API; graphs stay internal |
| 4 | FastAPI `Client` → `call_tool` / `list_tools` | **Valid** | Same pattern as official FastMCP client usage |
| 5 | MAF `MCPStreamableHTTPTool` → same servers | **Valid** | MCP is host-agnostic; one server, many orchestrators |
| 6 | Tool name prefixes (`document_*`, `voice_*`) in MAF | **Valid** | Avoids collisions when multiple MCP servers are attached |
| 7 | Class-based server (`BaseAgentMCPServer` + `register_tools`) | **Valid** | Thin wrapper over FastMCP; tools still registered normally |
| 8 | Health tools on each MCP | **Valid** | Operational probe + discoverable tool |
| 9 | stdio + HTTP dual mode | **Valid** | Local IDE vs service deployment |
| 10 | Not putting business logic only inside MAF | **Valid** | Specialists own side effects; orchestrator only plans |
| 11 | Expecting native Swagger on `:8001/docs` out of the box | **Not default** | MCP ≠ OpenAPI; see `/docs` section below — solvable |
| 12 | Using MCP as a public anonymous internet API | **Avoid** | Add auth / private network (same as any tool server) |

**Interview one-liner:** “FastMCP is correct here because document fill and voice HITL are **capabilities**; MCP is the **standard tool bus**; MAF/FastAPI are **hosts**.”

---

## Minimal FastMCP example (same shape as this repo)

```python
# example_document_mcp.py — pattern used by document-processing-mcp
from fastmcp import FastMCP

mcp = FastMCP(
    name="document_process_mcp",
    instructions="Fill a Word template from JSON. Tools: health, generate_document.",
)

@mcp.tool
def health() -> dict:
    """Liveness check."""
    return {"ok": True, "mcp": "document_process_mcp"}

@mcp.tool
def generate_document(template_path: str, data_json: str) -> dict:
    """Run the document pipeline (in real code: LangGraph)."""
    # ... invoke_document_graph(...)
    return {"ok": True, "output_path": "/data/out.docx"}

if __name__ == "__main__":
    # Clients connect to http://127.0.0.1:8001/mcp
    mcp.run(transport="http", host="127.0.0.1", port=8001)
```

**Client (FastAPI / scripts):**

```python
from fastmcp import Client

async def ping():
    async with Client("http://127.0.0.1:8001/mcp") as client:
        tools = await client.list_tools()
        print([t.name for t in tools])
        result = await client.call_tool("health", {})
```

**Repo equivalents**

| Piece | Path |
|---|---|
| Server | `document-processing-mcp/.../server.py`, `voice_enable_mcp/.../server.py` |
| Base class | `.../mcp/base.py` → `run_http()` / `run_stdio()` |
| Gateway client | `ip_api/.../mcp_client.py` |
| MAF attach | `central-agentic-flow/.../orchestrator.py` (`MCPStreamableHTTPTool`) |

**Mount MCP inside FastAPI** (official FastMCP pattern — useful if you want `/docs` on the same process):

```python
from fastapi import FastAPI
from fastmcp import FastMCP

mcp = FastMCP("document_process_mcp")
# ... register tools ...

mcp_app = mcp.http_app(path="/")          # MCP ASGI app
api = FastAPI(lifespan=mcp_app.lifespan)  # lifespan required
api.mount("/mcp", mcp_app)

# Human-facing OpenAPI lives on FastAPI:
# http://127.0.0.1:8001/docs
```

---

## Can we get FastMCP Swagger `/docs`?

### Short answer

| Question | Answer |
|---|---|
| Does FastMCP give `:8001/docs` like FastAPI by default? | **No** — HTTP transport speaks **MCP**, not OpenAPI |
| Can we still get a Swagger-style UI? | **Yes** — several options below |
| What do we have today? | Gateway Swagger: `http://127.0.0.1:8000/docs` (proxies under `/api/v1/agents/*`) + UI tool catalogue |

### Options (pick one)

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. Use gateway `/docs` (current)** | FastAPI already documents REST wrappers for MCP tools | Zero MCP change; one place for demos | Docs describe REST, not raw MCP JSON-RPC |
| **B. Mount MCP in FastAPI** | `api.mount("/mcp", mcp.http_app())` + add thin REST routes per tool | Native FastAPI `/docs` + MCP on same host | Slightly more plumbing |
| **C. Community `fastmcp-docs`** | Addon generates `/docs` + `/openapi.json` from tool metadata | Swagger-like UI for tools | Extra dependency; not core FastMCP |
| **D. Custom `@mcp.custom_route`** | Serve a static docs page / OpenAPI JSON yourself | Full control | You maintain the schema |

**FastMCP maintainers’ stance (summary):** they do **not** treat “expose every MCP tool as REST + Swagger” as a core goal (MCP is richer than plain REST). For interviews: “We use FastAPI OpenAPI for humans, MCP for agents.”

**Practical demo URLs in this stack**

```text
http://127.0.0.1:8000/docs              # FastAPI Swagger (incl. agent proxies)
http://127.0.0.1:8000/api/v1/agents/tools
http://127.0.0.1:8001/mcp               # MCP endpoint (not Swagger)
http://127.0.0.1:8002/mcp
```

---

## Can we use MLflow to monitor MCP LLMs and different LLMs?

### Short answer

**Yes — possible and a good fit.** MLflow GenAI Tracing can observe **multiple models and tool/agent steps** in one place. It does not replace MCP; it **observes** calls that happen inside or around MCP tools and orchestrators.

### What we would monitor in *this* repo

| LLM / component | Where it runs | What to trace |
|---|---|---|
| MAF orchestrator LLM | `central-agentic-flow` | Prompts, tool calls, final answer, tokens |
| Mapper LLM #1 | `document-processing-mcp` graph | Mapping prompt + JSON mapping |
| Validator LLM #2 | same document graph | Critique / pass-fail + retries |
| Speech / STT (if logged as spans) | `voice_enable_mcp` | Provider, latency (optional) |
| MCP tool spans | both MCPs + `ip_api` client | Tool name, args, result, latency, `xid` |

### How (conceptual wiring)

```text
mlflow.set_tracking_uri("http://mlflow:5000")
mlflow.set_experiment("document-agentic-flow")

# Auto where supported:
mlflow.langchain.autolog()   # document / voice LangGraph (LangChain stack)
mlflow.openai.autolog()      # OpenAI-compatible clients (mapper/validator/MAF if OpenAI SDK)

# Manual for MCP / custom:
@mlflow.trace(name="mcp.generate_document", span_type="TOOL")
def generate_document(...):
    ...
```

Tag each span/run with:

- `component` = `maf` | `document_mcp` | `voice_mcp` | `ip_api`
- `model` = deployment / model id
- `xid` = request correlation (already in this repo)
- `tool` = MCP tool name

Then in the **MLflow UI** you can filter “all mapper calls” vs “all MAF tool loops” vs “failed validations”.

### Feasibility table

| Goal | Possible with MLflow? | Notes |
|---|---|---|
| Trace several different LLMs in one experiment | **Yes** | Separate spans + model tags |
| See MCP tool calls next to LLM calls | **Yes** | Manual `@mlflow.trace` on tools + autolog on LLMs |
| Compare mapper vs validator quality over time | **Yes** | Evaluation / metrics on traces |
| Replace our SQLite `xid` trace logs | **Optional** | Can keep both; MLflow for GenAI UX, xid for ops |
| One-line autolog for FastMCP itself | **Limited** | FastMCP is not a first-class autolog target — wrap tools |
| Production sampling / async logging | **Yes** | MLflow tracing production guidance |

**Not required to change architecture:** add tracing at LLM call sites and MCP tool entrypoints; keep FastMCP as the tool bus.

---

## Related reading

- [README.md](README.md) — MCP elevator in this repo  
- [../flow-understanding/adding-a-new-flow.md](../flow-understanding/adding-a-new-flow.md)  
- [../maf-basic/06-tool-calling-and-hallucination.md](../maf-basic/06-tool-calling-and-hallucination.md)  
- FastMCP HTTP deployment: https://gofastmcp.com/deployment/http  
- MLflow GenAI tracing: https://mlflow.org/docs/latest/genai/tracing/
