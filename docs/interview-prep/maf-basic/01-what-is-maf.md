# 01 — What is MAF?

## Microsoft Agent Framework

Open framework (Python + .NET) to build production agents:

- Chat clients (OpenAI, Azure, Foundry, …)
- Tools (functions, **MCP**)
- Agents / workflows / hosting patterns

**Not a replacement for LangGraph** — complementary:

| | LangGraph | MAF |
|---|---|---|
| Strength | Explicit workflows, HITL, retries | Agent host + tool/MCP ecosystem |
| In this repo | Inside document & voice MCP | `central-agentic-flow` orchestrator |

---

## Core objects (Python)

```python
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(model="gpt-4o-mini", api_key="...")
agent = Agent(
    client=client,
    name="DocumentOrchestrator",
    instructions="You call MCP tools to help the user.",
    tools=[...],  # MCP servers or functions
)
response = await agent.run("Call both health tools and summarize")
print(response.text)
```

---

## MCP tool types in MAF

| Class | Transport |
|---|---|
| `MCPStdioTool` | Local subprocess stdio |
| `MCPStreamableHTTPTool` | HTTP MCP (what we use) |
| `MCPWebsocketTool` | WebSocket |

```python
async with MCPStreamableHTTPTool(
    name="document_process_mcp",
    url="http://127.0.0.1:8001/mcp",
    tool_name_prefix="document",
    approval_mode="never_require",
) as document_mcp:
    ...
```

**Interview:** “MCP is the USB-C of tools; MAF is one host that plugs in.”

Next: [02-agent-mcp-code.md](02-agent-mcp-code.md)
