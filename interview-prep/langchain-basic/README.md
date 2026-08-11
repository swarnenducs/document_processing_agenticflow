# LangChain basics — interview prep

> Honest review: the previous one-pager was **not enough** for a GenAI interview.  
> Use this folder end-to-end. Practice drawing the flows and typing the code from memory.

## Study order (2–3 hours)

| # | File | What you learn |
|---|---|---|
| 1 | [01-core-building-blocks.md](01-core-building-blocks.md) | Messages, chat models, prompts, parsers |
| 2 | [02-lcel-chains.md](02-lcel-chains.md) | LCEL `|` pipelines, invoke/stream/batch |
| 3 | [03-rag-with-langchain.md](03-rag-with-langchain.md) | **Full RAG flow + code** (load→split→embed→store→retrieve→generate) |
| 4 | [04-agents-tools-memory.md](04-agents-tools-memory.md) | Tools, agents, memory (vs LangGraph) |
| 5 | [05-this-repo-how-we-use-langchain.md](05-this-repo-how-we-use-langchain.md) | Mapper/validator chains in *this* project |
| 6 | [06-interview-qa.md](06-interview-qa.md) | Likely questions + crisp answers |

## One-line definitions

| Library | Role |
|---|---|
| **LangChain** | Building blocks for LLM apps (models, prompts, retrievers, LCEL) |
| **LangGraph** | Stateful **control flow** (graphs, retries, HITL) on top |
| **RAG** | Retrieve relevant docs → stuff into prompt → generate |

## What interviewers expect you to whiteboard

```text
1) Simple chain:   Prompt → ChatModel → OutputParser
2) RAG:            Docs → Split → Embed → VectorStore → Retriever → Prompt → LLM
3) Agent:          LLM ⇄ Tools (loop)   [or LangGraph for production control]
```

This repo’s document pipeline is closer to (1) + LangGraph, **not** classic RAG — but you **must** still know RAG for GenAI roles.
