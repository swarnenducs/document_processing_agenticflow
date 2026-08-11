# 06 — Tool calling & hallucination control (MAF)

## Are we using an LLM for tool calling?

**Yes.** In this repo MAF is:

```text
User message
  → OpenAI-compatible chat model (OpenAI / Azure OpenAI / Groq / compatible)
  → Agent Framework binds MCP tools as callable functions
  → Model emits tool calls (name + JSON args)
  → Runtime executes tools against FastMCP HTTP servers
  → Tool results return to the model
  → Model writes the final natural-language answer
```

Code: `central-agentic-flow/src/central_agentic_flow/orchestrator.py` — `Agent(..., tools=[document_mcp, voice_mcp])` + `agent.run(message)`.

So the LLM decides **which** tool and **with what arguments**. The MCP / LangGraph decides **what is true** (files created, HITL status, errors).

## Where hallucination can appear

| Risk | Example |
|---|---|
| Fake tool outcomes | “Document saved at `/tmp/foo.docx`” without calling `document_generate_document` |
| Wrong args | Invented `template_path` / contract reference |
| Skipping HITL | Claiming contract created when voice tool returned `needs_confirmation` |
| Over-confident summary | Ignoring tool `ok: false` / error fields |

## How we manage hallucination (this design)

### 1. Ground answers in tool results (instructions)

`orchestrator_instructions.md` tells the agent to:

- Prefer calling tools over inventing paths/results
- Include tool outcomes (paths, ids, status, errors)
- Follow confirm flow for voice (`start` → user confirm → `confirm`)

### 2. Tools are the source of truth (typed side effects)

MCP tools return structured JSON (`ok`, `error`, `xid`, file paths, `status`).  
LangGraphs validate inputs (template exists, JSON parse, entity match).  
The LLM should **summarize** those payloads, not replace them.

### 3. Narrow tool surface + clear names

- Few tools with strong docstrings
- Prefixes `document_*` / `voice_*` avoid ambiguity
- UI shows the live catalogue under **Available MCP tools**

### 4. Human-in-the-loop where mistakes are costly

Voice contract creation can pause (`needs_confirmation` / LangGraph `interrupt`) before write.  
That is a product-level guard against the model “confirming” silently.

### 5. Separation: mapper/validator LLMs ≠ MAF orchestrator

Document quality uses a separate **mapper** + **validator** (LLM #1 / #2) inside the document graph, with retries.  
Even if MAF hallucinates a cheerful summary, a failed validation still fails the job.

### 6. Observability (xid / traces)

Correlate HTTP → MCP → LLM via `xid` so you can prove whether a tool ran and what it returned (UI **Trace Logs** tab).

### 7. What we do **not** fully automate yet (honest gaps)

| Control | Status in repo |
|---|---|
| Forced tool use / “must call tool” for certain intents | Prompt-only (not hard schema routing) |
| MAF `approval_mode` for every tool call | Currently `never_require` (local DX); tighten for prod |
| Structured output schema for final answer | Free-form text from `agent.run` |
| Server-side post-check that answer cites tool JSON | Not enforced — rely on instructions + HITL |

**Interview line:** “We don’t try to make the LLM truthful in the abstract — we make side effects go through MCP tools, keep HITL on irreversible steps, and treat tool JSON as ground truth.”

## Practical hardening checklist (if asked “how would you improve?”)

1. Set `approval_mode` / human approval for write tools in production.
2. Add a thin post-processor: if the model claims success but no successful tool result in the turn → rewrite/fail.
3. Use stricter system prompts + few-shot tool traces.
4. Lower temperature for the orchestrator model.
5. Eval suite: golden asks → expected tool names + required fields in tool results (Foundry continuous eval / batch eval).

Next: [07-azure-foundry-deploy-and-auth.md](07-azure-foundry-deploy-and-auth.md)
