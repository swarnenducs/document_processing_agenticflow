# 05 — LangGraph interview Q&A

**Q: LangGraph vs LangChain?**  
A: LangChain = building blocks. LangGraph = stateful control flow (edges, retries, HITL).

**Q: What is a checkpointer?**  
A: Persistence layer for graph state between invocations, keyed by thread_id.

**Q: Do you use memory in voice?**  
A: Yes — SQLAlchemy checkpointer + `thread_id` so `interrupt()` can pause and resume confirmation. Not chat-buffer memory; workflow checkpoint memory. Survives MCP restart because rows live in SQLite / Azure SQL. Completed contracts also land in `voice_contracts`.

**Q: Does document graph use a checkpointer?**  
A: No. One-shot job; retries happen inside a single run via state.

**Q: How does HITL work?**  
A: Node calls `interrupt(payload)` → graph pauses → client gets thread_id → later `invoke(Command(resume=...), config=thread_id)`.

**Q: Why not Postgres/Redis checkpointer?**  
A: Official LangGraph savers target Postgres or sqlite3. Default here is SQLAlchemy on SQLite / Azure SQL. Redis is a one-env swap: `LANGGRAPH_CHECKPOINT_BACKEND=redis` + `REDIS_URL` — vanilla Redis, not Redis Stack.

**Q: State vs checkpointer?**  
A: State is the data shape for one run. Checkpointer stores snapshots of that state across runs/turns.

Practice: draw voice flow with interrupt, then explain why document doesn’t need it.
