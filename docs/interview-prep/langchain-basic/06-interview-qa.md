# 06 — LangChain interview Q&A

**Q: What is LangChain?**  
A: A framework of composable primitives for LLM apps — chat models, prompts, parsers, retrievers, tools — often wired with LCEL (`|`).

**Q: What is LCEL?**  
A: LangChain Expression Language: Runnables you compose with `|`, supporting invoke/stream/batch uniformly.

**Q: Explain RAG.**  
A: Index docs (split+embed+store). At query time retrieve top-k chunks, put them in the prompt, then generate. Reduces hallucinations on private data.

**Q: Write RAG steps.**  
A: Load → Split → Embed → VectorStore → Retriever → Prompt(context, question) → LLM.

**Q: Chunk size?**  
A: Trade-off; start ~500–1000 chars with overlap; tune with retrieval eval.

**Q: Embeddings vs chat model?**  
A: Embeddings map text→vectors for search; chat model generates language. Different APIs/costs.

**Q: FAISS vs Chroma vs Pinecone?**  
A: FAISS local/dev; Chroma easy local persistent; Pinecone/managed for production scale.

**Q: How do you evaluate RAG?**  
A: Retrieval hit-rate, faithfulness, answer relevance; golden Q&A set; ragas-style metrics.

**Q: Agent vs chain?**  
A: Chain is fixed; agent chooses tools dynamically. Prefer graphs (LangGraph) when control must be explicit.

**Q: Structured output?**  
A: `with_structured_output(PydanticModel)` or JSON schema — validates LLM output.

**Q: How does your project use LangChain?**  
A: Dual chat models via factory, YAML ChatPromptTemplates, structured mapping/validation inside LangGraph nodes — not classic vector RAG.

**Q: Temperature?**  
A: 0 for extraction/mapping; higher for brainstorming. We keep mapper/validator low for determinism.

Practice: redraw RAG from memory, then type the FAISS example without looking.
