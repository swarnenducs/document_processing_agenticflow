# Q&A bank (speak answers out loud)

## Architecture

**Q: Explain the system in 60 seconds.**  
A: See [00-elevator-pitch.md](../00-elevator-pitch.md).

**Q: Why split into multiple processes?**  
A: Independent deploy/scale; clear ownership; MCP tools reusable by MAF and API; each folder can become its own git.

**Q: Is this multi-agent?**  
A: Specialist workers (document/voice graphs) + MAF orchestrator. Without MAF it’s a multi-LLM/multi-tool pipeline. With MAF it’s orchestrated multi-agent style.

**Q: Where do prompts live?**  
A: Per component — document YAML under `document-processing-mcp/prompts/`, MAF instructions under `central-agentic-flow/prompts/`.

---

## Memory

**Q: Are we using any memory in voice?**  
A: **Yes.** Voice LangGraph uses `MemorySaver` (checkpointer) + `thread_id` so HITL `interrupt()` can pause and resume. Completed contracts are also stored in SQLite. This is workflow checkpoint memory, not a full chat-history buffer.

**Q: Document graph memory?**  
A: No checkpointer — one-shot job; retries use in-run `retry_count`.

**Q: MAF memory?**  
A: `/ask` is currently stateless per call. Multi-turn orchestrator memory would need a session store.

**Q: Types of memory?**  
A: Conversation buffer, summary, LangGraph checkpoint, long-term entity store, RAG. See `langgraph-basic/04-memory-management.md`.

---

## LangGraph

**Q: What is state?**  
A: Typed shared memory between nodes; artifacts + status/errors for routing.

**Q: How does retry work?**  
A: Conditional edge after validate → bump_retry → map_fields until max_retries.

**Q: Pipeline vs agent?**  
A: Pipeline = fixed graph. Agent = model chooses tools. We use graphs for reliability; MAF for NL routing.

---

## LangChain / LLMs

**Q: What is LCEL? Show a chain.**  
A: `prompt | llm | StrOutputParser()` — composable Runnables with invoke/stream/batch.

**Q: Explain RAG end-to-end.**  
A: Load → split → embed → vector store (index). Query: embed question → retrieve top-k → prompt(context, question) → LLM. See `interview-prep/langchain-basic/03-rag-with-langchain.md`.

**Q: Why two LLMs?**  
A: Separation of concerns — mapper fills; validator critiques. Different models/providers/cost profiles.

**Q: How do you switch providers?**  
A: Env (`MAPPER_PROVIDER`, `VALIDATOR_PROVIDER`, model ids) via factory — no node rewrite.

**Q: How do you reduce hallucinations?**  
A: Schema validation, critic LLM, confidence scores, HITL on voice, retries. For RAG: ground in retrieved context + “say I don’t know”.

**Q: Does this product use RAG?**  
A: Primary path is structured JSON→Word mapping via LangGraph, not vector RAG. RAG would be an add-on (clause library / policy retrieval).

---

## FastAPI

**Q: Why async jobs?**  
A: LLM+DOCX are slow; return job_id; progress via WebSocket/poll.

**Q: What is xid?**  
A: Request correlation id propagated to logs/tools/LLM traces.

---

## MCP

**Q: What is MCP?**  
A: Standard for exposing tools to LLM hosts. FastMCP HTTP servers here.

**Q: Why MCP not only REST?**  
A: Tool schemas for agents; same capability for MAF, IDEs, other orchestrators.

---

## MAF

**Q: Role of MAF?**  
A: NL orchestrator calling MCP tools — does not own LangGraph pipelines.

**Q: MAF vs LangGraph?**  
A: Complementary — LangGraph inside specialists; MAF above them.

---

## Design / trade-offs

**Q: Why duplicate shared code instead of a shared library?**  
A: Each component stays self-contained for separate repos; accept duplication for deploy independence.

**Q: Single replica WebSockets?**  
A: In-process hub OK locally; Redis/pubsub for multi-instance.

**Q: Biggest production risk?**  
A: Cost/latency of dual LLMs, prompt drift, MCP auth, HITL timeouts, storage consistency across services.

---

## Behavioral / coding prompts they may give

1. “Draw the document graph and add a new `redact_pii` node.”  
2. “How would you add auth to MCP?”  
3. “Replace SQLite with Postgres — what breaks?”  
4. “MAF tool fails halfway — how do you make it idempotent?”  

Prepare: state changes, edges, error handling, observability.
