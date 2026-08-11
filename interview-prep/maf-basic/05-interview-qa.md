# 05 — MAF interview Q&A

**Q: What is MAF?**  
A: Microsoft Agent Framework — build agents with LLM clients and tools (including MCP).

**Q: MAF vs LangGraph in your project?**  
A: LangGraph runs specialist pipelines (document/voice). MAF is the NL orchestrator that calls those pipelines as MCP tools.

**Q: Why MCP under MAF?**  
A: Standard tool interface; same servers usable by API proxies, MAF, or other hosts.

**Q: Does MAF keep chat memory today?**  
A: No — each `/ask` is independent. Voice HITL memory is in the voice graph’s `MemorySaver`.

**Q: How would you add multi-turn MAF memory?**  
A: Agent session or persist message history per user/conversation id; still keep specialist HITL in LangGraph checkpoints.

**Q: Tool name collisions?**  
A: `tool_name_prefix` → `document_health` vs `voice_health`.

**Q: approval_mode?**  
A: Local automation uses `never_require`; production may require human approval for sensitive tools.

**Q: Does MAF use an LLM for tool calling?**  
A: Yes — the chat model selects tools and args; MCP/LangGraph execute side effects and return JSON ground truth.

**Q: How do you control hallucination?**  
A: Instructions to prefer tools; structured tool results; HITL on voice confirms; separate mapper/validator in document graph; xid traces. See [06-tool-calling-and-hallucination.md](06-tool-calling-and-hallucination.md).

**Q: How do you deploy this on Azure AI Foundry?**  
A: Either host the agent in Foundry (instructions + tools → MCP/REST) or keep our MAF container and point `MAF_PROVIDER=azure_openai` at a Foundry/AOAI deployment. Auth: Entra for users, managed identity for service→model/tools. See [07-azure-foundry-deploy-and-auth.md](07-azure-foundry-deploy-and-auth.md).

**Q: How do you add a new flow?**  
A: Implement in an MCP (+ LangGraph), expose tools, attach MCP in orchestrator (or reuse existing), update instructions; optional API/UI. See [../flow-understanding/adding-a-new-flow.md](../flow-understanding/adding-a-new-flow.md).
