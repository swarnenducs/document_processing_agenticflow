# 05 — LangGraph interview Q&A

**Q: LangGraph vs LangChain?**  
A: LangChain = building blocks. LangGraph = stateful control flow (edges, retries, HITL).

**Q: What is a checkpointer?**  
A: Persistence layer for graph state between invocations, keyed by thread_id.

**Q: Do you use memory in voice?**  
A: Yes — `MemorySaver` + `thread_id` so `interrupt()` can pause and resume confirmation. Not chat-buffer memory; workflow checkpoint memory. Completed contracts also land in SQLite.

**Q: Does document graph use MemorySaver?**  
A: No. One-shot job; retries happen inside a single run via state.

**Q: How does HITL work?**  
A: Node calls `interrupt(payload)` → graph pauses → client gets thread_id → later `invoke(Command(resume=...), config=thread_id)`.

**Q: MemorySaver in production?**  
A: Replace with Postgres/Redis checkpointer for multi-instance and durability.

**Q: State vs checkpointer?**  
A: State is the data shape for one run. Checkpointer stores snapshots of that state across runs/turns.

Practice: draw voice flow with interrupt, then explain why document doesn’t need it.
