# MCP basics (Model Context Protocol)

## Elevator

> **MCP** is an open protocol so an LLM host can discover and call **tools** on a server in a standard way (like USB for AI tools).  
> This project uses **FastMCP** HTTP servers so FastAPI and MAF can call the same tools.

## Docs in this folder

| File | Topic |
|---|---|
| [README.md](README.md) (this file) | MCP elevator + this repo’s servers |
| [02-fastmcp-mlflow-docs-validity.md](02-fastmcp-mlflow-docs-validity.md) | **Use-case validation table**, FastMCP examples, `/docs` Swagger options, **MLflow** multi-LLM monitoring |
| [../../FASTMCP_JSON.md](../../FASTMCP_JSON.md) | Tool result: structured JSON object vs JSON text |

## Why MCP in interviews?

Shows you understand **tool boundaries** and **service separation**, not only notebooks.

## This repo’s MCP servers

| Server | Port | Tools (examples) |
|---|---|---|
| `document-processing-mcp` | 8001 `/mcp` | `health`, `generate_document` |
| `voice_enable_mcp` | 8002 `/mcp` | `health`, `start_voice_contract`, `confirm_voice_contract`, `list_voice_contracts` |

Each MCP **owns its LangGraph** — tools are the public API.

## Transports

| Transport | Use |
|---|---|
| **stdio** | Local IDE / single process |
| **HTTP (streamable)** | Microservices — what we use for FastAPI/MAF |

Interview: “HTTP MCP lets us scale and deploy workers independently.”

## Call paths

```text
1) FastAPI /api/v1/agents/*  → FastMCP Client → tool
2) MAF Agent                 → MCPStreamableHTTPTool → tool
```

Same tools, two hosts.

## Tool naming collision

Both servers have `health`. MAF uses prefixes: `document_health`, `voice_health`.

## Security talking points

- Don’t expose MCP publicly without auth
- Treat tool args as untrusted input
- Prefer least-privilege tools (no raw shell)

## Common interview Qs

**Q: MCP vs OpenAPI?**  
A: MCP is optimized for LLM tool discovery/calling; OpenAPI is general HTTP for humans/services. We use both (FastAPI OpenAPI + MCP tools). FastMCP does **not** ship `/docs` by default — see [02-fastmcp-mlflow-docs-validity.md](02-fastmcp-mlflow-docs-validity.md).

**Q: Why not put LangGraph inside FastAPI only?**  
A: MCP makes the pipeline a reusable capability for any orchestrator (MAF, Cursor, other agents).

**Q: Can MLflow monitor our LLMs?**  
A: Yes — trace MAF + mapper + validator (+ MCP tool spans). Details in the validity doc.

## Point to code

- `document-processing-mcp/src/document_processing_mcp/server.py`
- `voice_enable_mcp/src/voice_enable_mcp/server.py`
- `ip_api/src/ip_api/mcp_client.py`
- `docs/MCP_AGENTS.md`
