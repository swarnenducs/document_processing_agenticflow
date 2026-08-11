# Resume bullets — Intelligent Pricing Platform

Copy–paste ready lines for your resume / LinkedIn. Pick **4–6** strongest bullets (don’t dump all).  
Adjust metrics only if you can defend them in interview (latency, % accuracy, users, etc.).

---

## Project title options (pick one)

| Style | Line |
|---|---|
| Formal | **Intelligent Pricing Platform** — Multi-agent GenAI platform for quote-to-contract automation (pricing + renewal) |
| Short | **Agentic Document & Voice Contract Platform** (LangGraph · MCP · MAF · FastAPI) |
| Cloud-leaning | **GenAI Document Orchestration System** with Microsoft Agent Framework + FastMCP microservices |

---

## One-line summary (under the title)

Built a **separately deployable** agentic GenAI stack for **auto contract pricing + quote-to-contract**: FastAPI gateway + Gradio UI, specialist **FastMCP** services for pricing/contract generation, and a **Microsoft Agent Framework (MAF)** central agent that routes natural-language asks to MCP tools over HTTP.

---

## Strong resume bullets (recommended)

- Designed and implemented a **multi-component GenAI architecture** (UI, API gateway, document MCP, voice MCP, MAF orchestrator) so each service is independently runnable and deployable (Docker Compose / local launcher).
- Implemented an **agentic pricing-to-contract flow**: pricing agents segment inputs → structured outcomes for an **LLM + an integrated legacy predictive model (black-box)** to compute the final quote price.
- Built **LangGraph pipelines** to transform structured pricing/contract inputs into **validated outputs** (mapping/validation with retry) so contract artifacts remain consistent and grounded.
- Implemented a separate **LangGraph voice/renewal workflow** with **human-in-the-loop (HITL)** confirmation using checkpointer/`thread_id` so voice can **renew** or **finalize** a contract before it’s generated.
- Exposed specialist capabilities as **FastMCP HTTP tools** so the same pricing/contract capabilities are reusable by FastAPI proxies and orchestrated by the MAF central agent.
- Developed a **Microsoft Agent Framework (MAF) central agent** that uses LLM **tool calling** against MCP servers for natural-language orchestration, keeping pricing/contract business logic inside specialist graphs (not inside the orchestrator).
- Built a **FastAPI gateway** with async document jobs, file uploads, **WebSocket live progress**, OpenAPI `/docs`, MCP proxies, and `POST /api/ask` proxy to the MAF service.
- Added **request correlation (`xid`)** and SQLite-backed **session IDs** (with optional user id/email) across document, voice, and MAF flows for traceability and multi-turn client continuity.
- Separated **component-owned prompts** (YAML/MD per service) and env-driven LLM providers (OpenAI / Azure OpenAI / Groq) for mapper, validator, speech, and orchestrator models.
- Delivered a **Gradio UI** for document generation, voice/chat contract creation, central-agent chat, live API/MAF health, and MCP tool catalogue visibility.

---

## Shorter bullets (if space is tight)

- Built end-to-end **agentic document + voice contract** system with **LangGraph**, **FastMCP**, and **MAF** orchestration.
- Implemented **HITL** voice contract confirmation and **LLM map/validate** Word generation with retries.
- Designed **microservice-style GenAI components** (API, MCPs, MAF, UI) with Docker Compose and shared HTTP tool contracts.
- Added **observability hooks** (`xid` tracing, session store) and Gradio UX for jobs, voice, and central agent asks.

---

## Skills / keywords to list nearby

`Python` · `FastAPI` · `LangChain` · `LangGraph` · `LCEL` · `MCP` · `FastMCP` · `Microsoft Agent Framework (MAF)` · `Azure OpenAI / Foundry (deploy path)` · `Tool calling` · `HITL` · `RAG concepts` · `WebSockets` · `SQLite` · `Docker` · `Gradio` · `Prompt engineering` · `GenAI observability (xid / MLflow-ready)`

---

## LinkedIn “Featured / Project” blurb (3–4 lines)

> Multi-component GenAI platform that generates styled Word documents from JSON and creates contracts from voice/text with human confirmation.  
> Specialists run as **LangGraph + FastMCP** services; a **MAF** central agent orchestrates them via tool calling.  
> FastAPI gateway handles jobs, WebSockets, and `/api/ask`; Gradio UI for operators.  
> Designed for independent deploy of each component and future Azure AI Foundry hosting.

---

## Interview talking points (tie resume → story)

| Resume claim | Be ready to explain |
|---|---|
| Separately deployable | Folders + ports 7860/8000/8001/8002/8003 + compose |
| Dual LLM | Mapper vs validator; why not one model |
| HITL | Voice interrupt / confirm; why MemorySaver ≠ MAF session |
| MCP | Tools as public API; prefixes `document_` / `voice_` |
| MAF | Orchestrator only; no business logic inside agent |
| Session / xid | Correlation vs conversation memory |

---

## What *not* to over-claim

| Avoid unless true | Safer phrasing |
|---|---|
| “Production at scale for N users” | “Local/dev stack with production-oriented architecture” |
| “Fully eliminated hallucination” | “Grounded answers via MCP tool results + HITL on irreversible steps” |
| “Deployed to Azure Foundry” | “Designed for Foundry/MAF deploy; documented Entra / MI auth path” |
| Exact % quality gains | “LLM validation + retry loop to improve mapping quality” |

---

## ATS-friendly single block (copy)

**Intelligent Pricing Platform** | GenAI / Agentic Systems  
*Python, FastAPI, LangGraph, FastMCP, Microsoft Agent Framework, Gradio, Docker*

- Architected a multi-service **agentic pricing-to-contract** platform: pricing agents segment inputs, then use an **integrated legacy predictive model (black-box)** + LLM to compute quote price and drive quote-to-contract generation.
- Implemented **LangGraph pipelines** for structured data mapping/validation (with retry) and for contract lifecycle generation with grounded outputs.
- Built **FastMCP HTTP tool servers** (pricing/contract tools) and a **MAF central agent** that performs natural-language **tool orchestration**; FastAPI gateway with async jobs, WebSockets, and `xid` correlation.
- Added **voice-driven renew/finalize** contract workflow with **human-in-the-loop (HITL)** confirmation (`thread_id` / checkpointer) before the final contract artifact is produced.

---

## ATS-friendly single block — Trade Finance (TraydCheck & TraydGuard)

**TraydCheck & TraydGuard** | Trade Finance AI Platform  
*Python, FastAPI, Asyncio, PyTorch, TensorFlow, BERT, LLMs, LangChain, LangGraph, ChromaDB, YOLO, Kafka, Redis, MongoDB, Docker, MLflow, GitHub Actions*

- Built an **AI-powered Trade Finance document platform** for automated **classification, UCP/compliance verification, and fraud/anomaly detection**, aligned with global banking and letter-of-credit standards.
- Implemented a **LangGraph compliance workflow** that orchestrates document intake → classification → UCP/rule checks → anomaly/fraud flags with stateful retries and auditable step outcomes.
- Developed multiple **RAG pipelines** with **LangChain + ChromaDB + MongoDB Vector Search** to ground compliance checks against trade rules and historical document context.
- Trained/deployed **document classification models (CNN, BERT)** for LCs, invoices, and compliance docs; applied **YOLO-based layout detection** for scanned trade document structure analysis.
- Designed **event-driven microservices** with **FastAPI (async), Kafka, and Redis** to serve real-time, low-latency ML inference APIs across the Trade Finance workflow.
- Implemented **MLOps** (MLflow, Docker, GitHub Actions) for model versioning, CI/CD, monitoring, plus **real-time anomaly detection and audit-trail automation** to strengthen compliance accuracy and regulatory alignment.
