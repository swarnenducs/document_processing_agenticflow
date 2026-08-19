# Elevator pitch (memorize)

## 30-second version

> This is a **multi-component GenAI document system**: a FastAPI gateway, Gradio UI, two **FastMCP** specialist servers (document fill + voice contract), and a **Microsoft Agent Framework (MAF)** orchestrator.  
> Document and voice each run their **own LangGraph**. Prompts live **inside each component**. MAF only decides **which MCP tools to call** over HTTP — it does not own the pipelines.

## 2-minute version

1. **Problem:** Fill styled Word contracts from JSON / voice, with validation and human confirmation.  
2. **Document path:** LangGraph = extract styles → LLM map → generate DOCX → LLM validate → optional retry.  
3. **Voice path:** Separate LangGraph = parse transcript → HITL confirm → create contract.  
4. **API:** Jobs, uploads, WebSocket progress, proxies to MCP.  
5. **MAF:** `POST /ask` → agent with tool-calling against MCP1 + MCP2.  
6. **Deploy shape:** Each folder is self-contained (can become its own git); `run_all_components.py` / Docker Compose for local.

## Keywords interviewers listen for

- Typed **state**, **nodes**, **conditional edges**, **retry**
- **Dual LLM roles** (mapper vs validator) + env-driven providers
- **MCP** as tool boundary (HTTP streamable)
- **Orchestrator vs specialist** (MAF vs LangGraph workers)
- **HITL** (human-in-the-loop) interrupts / confirm
- **Observability** (xid / request correlation)

## What this is *not*

- Not “one giant LangChain chain”
- Not multi-agent *until* MAF (or similar) orchestrates specialists
- Not embedding all business logic in FastAPI
