# MAF basics — interview prep

Microsoft Agent Framework as used in `central-agentic-flow`, with code and comparison to LangGraph.

## Study order

| # | File |
|---|---|
| 1 | [01-what-is-maf.md](01-what-is-maf.md) |
| 2 | [02-agent-mcp-code.md](02-agent-mcp-code.md) — Agent + MCP tools code |
| 3 | [03-architecture-in-this-repo.md](03-architecture-in-this-repo.md) |
| 4 | [04-memory-and-sessions.md](04-memory-and-sessions.md) |
| 5 | [05-interview-qa.md](05-interview-qa.md) |
| 6 | [06-tool-calling-and-hallucination.md](06-tool-calling-and-hallucination.md) — LLM tools + grounding |
| 7 | [07-azure-foundry-deploy-and-auth.md](07-azure-foundry-deploy-and-auth.md) — Foundry + Entra |
| 8 | [08-session-context-architecture-changes.md](08-session-context-architecture-changes.md) — multi-turn context over flow results |

## Elevator

> MAF hosts an **LLM agent** that can call **MCP tools**.  
> Our MAF service does **not** own document/voice LangGraphs — it orchestrates them over HTTP.
