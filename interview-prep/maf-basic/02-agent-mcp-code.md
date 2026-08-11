# 02 — Agent + MCP code (this repo pattern)

From `central-agentic-flow/.../orchestrator.py` (simplified):

```python
async def ask_maf(message: str, *, instructions: str | None = None):
    from agent_framework import Agent, MCPStreamableHTTPTool
    from agent_framework.openai import OpenAIChatClient

    client = resolve_maf_chat_client()  # OpenAI / Azure / Groq via env
    system = instructions or load_maf_instructions()

    async with (
        MCPStreamableHTTPTool(
            name="document_process_mcp",
            url=os.getenv("DOCUMENT_MCP_URL", "http://127.0.0.1:8001/mcp"),
            tool_name_prefix="document",
            approval_mode="never_require",
            request_timeout=300,
        ) as document_mcp,
        MCPStreamableHTTPTool(
            name="voice_process_mcp",
            url=os.getenv("VOICE_MCP_URL", "http://127.0.0.1:8002/mcp"),
            tool_name_prefix="voice",
            approval_mode="never_require",
            request_timeout=300,
        ) as voice_mcp,
        Agent(
            client=client,
            name="DocumentOrchestrator",
            instructions=system,
            tools=[document_mcp, voice_mcp],
        ) as agent,
    ):
        response = await agent.run(message)

    return response.text, response.response_id
```

## What happens at runtime

```text
User: "Generate document with template T and data D"
  → MAF LLM plans tool use
  → calls document_generate_document(...)
  → document MCP runs LangGraph
  → tool result back to MAF
  → MAF writes natural-language summary
```

## Why `tool_name_prefix`

Both MCPs expose `health` → become `document_health` / `voice_health`.

## HTTP service wrapper

`central-agentic-flow` FastAPI:

- `POST /ask`
- `GET /health`, `GET /ask/health`

`ip_api` proxies `POST /api/ask` → `MAF_BASE_URL`.

Next: [03-architecture-in-this-repo.md](03-architecture-in-this-repo.md)
