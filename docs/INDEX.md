# Documentation index

Every markdown file in this repo that is meant to be read (not runtime prompt YAML).  
**Start here:** pick a row in [By task](#by-task), or scan [All documents](#all-documents).

Runtime prompts (edit to change model behaviour) live next to each component — they are listed at the bottom but are not guides.

---

## By task

| If you want to… | Open |
|-----------------|------|
| Install and run locally (macOS/Linux) | [../README.md](../README.md) |
| Install and run on Windows | [../install.ps1](../install.ps1) (`.\install.ps1`) |
| See ports and package layout | [COMPONENTS.md](COMPONENTS.md) |
| Understand the architecture | [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) |
| Call HTTP / WS / MCP APIs | [api-details-information.md](api-details-information.md) |
| Hit APIs from Postman | [POSTMAN.md](POSTMAN.md) |
| Local vs Azure SQL/Blob + admin templates | [LOCAL_AND_CLOUD_STORAGE.md](LOCAL_AND_CLOUD_STORAGE.md) |
| See every env variable (tables by component) | [ENVIRONMENT.md](ENVIRONMENT.md) |
| Dynaconf later + Azure Web App JSON + Key Vault | [DYNACONF.md](DYNACONF.md) |
| Estimate LLM tokens / STT cost | [TOKEN_CONSUMPTION.md](TOKEN_CONSUMPTION.md) |
| Route cheap vs strong document mappers | [DOCUMENT_LLM_OPTIMIZATION.md](DOCUMENT_LLM_OPTIMIZATION.md) |
| Voice → contract HITL | [VOICE_CONTRACT_FLOW.md](VOICE_CONTRACT_FLOW.md) |
| Deploy Azure Web Apps | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
| Deploy Foundry-hosted MAF | [FOUNDRY_HOSTED_MAF.md](FOUNDRY_HOSTED_MAF.md) |
| Add a chat or metadata MCP to MAF | [ADD_MAF_MCP_AGENTS.md](ADD_MAF_MCP_AGENTS.md) |
| Prepare for interviews | [interview-prep/README.md](interview-prep/README.md) |

---

## All documents

### Repo root

| Document | Description |
|----------|-------------|
| [../README.md](../README.md) | Project overview, LLM roles, UV/pip setup, sample files, how to run the stack |
| [../AGENTS.md](../AGENTS.md) | Local-only agent rules (gitignored; not in commits) |
| [../install.ps1](../install.ps1) | Windows one-shot: uv, Python, workspace deps, `.env` scaffold |

### Guides (`docs/`)

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Short docs landing page (points here for the full catalogue) |
| [INDEX.md](INDEX.md) | This file — complete catalogue with one-line descriptions |
| [COMPONENTS.md](COMPONENTS.md) | Five packages, ports, prompt folders, Docker and split-repo notes |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Architecture walkthrough and interview talking points for this codebase |
| [INTERVIEW_LANGGRAPH.md](INTERVIEW_LANGGRAPH.md) | LangGraph in this repo: state, edges, retries, dynamic models |
| [VOICE_CONTRACT_FLOW.md](VOICE_CONTRACT_FLOW.md) | Voice/text → intent → catalog lookup → HITL confirm → contract file |
| [LOCAL_AND_CLOUD_STORAGE.md](LOCAL_AND_CLOUD_STORAGE.md) | SQLite + local files vs Azure SQL + Blob; default admin template library (`ipp_default_template`) |
| [ENVIRONMENT.md](ENVIRONMENT.md) | Env variables in tables: what each does and which process reads it (`DEBUG_FLOW` included) |
| [DYNACONF.md](DYNACONF.md) | Env overlay for Dynaconf later; Key Vault; Azure Web App example JSON per component |
| [api-details-information.md](api-details-information.md) | Catalogue of gateway, MAF, document MCP, and voice MCP APIs |
| [POSTMAN.md](POSTMAN.md) | Import Postman collection; gateway REST + MAF `/invoke` |
| [TOKEN_CONSUMPTION.md](TOKEN_CONSUMPTION.md) | Estimated tokens (and Whisper minutes) per component, with cost knobs |
| [DOCUMENT_LLM_OPTIMIZATION.md](DOCUMENT_LLM_OPTIMIZATION.md) | Optional optimized mapper flow: JSON config, complexity + retry cascade |
| [MCP_AGENTS.md](MCP_AGENTS.md) | Class-based FastMCP servers for document (`:8001`) and voice (`:8002`) |
| [FASTMCP_JSON.md](FASTMCP_JSON.md) | How FastMCP returns Pydantic JSON (`structuredContent`) vs text blocks |
| [MAF_LOCAL.md](MAF_LOCAL.md) | Run the MAF orchestrator locally (`:8003`), prompts and registry |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Azure Web Apps + GitHub Actions for API and UI |
| [CICD_AZURE.md](CICD_AZURE.md) | Short pointer to `DEPLOYMENT_GUIDE.md` |
| [AZURE_DEPLOY_MAF.md](AZURE_DEPLOY_MAF.md) | Full MAF deploy: Foundry model, hosted agent, five Web Apps |
| [FOUNDRY_HOSTED_MAF.md](FOUNDRY_HOSTED_MAF.md) | Focused runbook for Foundry-hosted MAF (chat only; jobs stay on Web App) |
| [ADD_MAF_MCP_AGENTS.md](ADD_MAF_MCP_AGENTS.md) | Attach optional chat (ask) and metadata (jobs) MCPs via config URLs |

### Component READMEs

| Document | Description |
|----------|-------------|
| [../ip_api/README.md](../ip_api/README.md) | FastAPI gateway (`:8000`) — install and run this package alone |
| [../document-processing-mcp/README.md](../document-processing-mcp/README.md) | Document LangGraph FastMCP (`:8001`) |
| [../voice_enable_mcp/README.md](../voice_enable_mcp/README.md) | Voice contract FastMCP (`:8002`) |
| [../central-agentic-flow/README.md](../central-agentic-flow/README.md) | MAF orchestrator (`:8003`) |
| [../UI/README.md](../UI/README.md) | Gradio UI (`:7860`) |
| [../tests/README.md](../tests/README.md) | How to run pytest (workspace vs one package) |

### Runtime prompts (not guides)

| Document | Description |
|----------|-------------|
| [../prompts/README.md](../prompts/README.md) | Pointer: prompts moved into each component folder |
| [../document-processing-mcp/prompts/](../document-processing-mcp/prompts/) | Mapper, validator, extraction critic, optional agent YAML |
| [../voice_enable_mcp/prompts/README.md](../voice_enable_mcp/prompts/README.md) | Voice intent + confirm YAML (LCEL) |
| [../central-agentic-flow/prompts/README.md](../central-agentic-flow/prompts/README.md) | MAF orchestrator prompt location |
| [../central-agentic-flow/prompts/orchestrator_instructions.md](../central-agentic-flow/prompts/orchestrator_instructions.md) | MAF system preamble (chat `/ask` only) |

---

## Interview prep (`docs/interview-prep/`)

| Document | Description |
|----------|-------------|
| [interview-prep/README.md](interview-prep/README.md) | Study plan and folder map for GenAI interviews |
| [interview-prep/00-elevator-pitch.md](interview-prep/00-elevator-pitch.md) | 60-second pitch of this system |
| [interview-prep/resume-bullets.md](interview-prep/resume-bullets.md) | Resume / LinkedIn lines for the project |
| [interview-prep/Course_link.md](interview-prep/Course_link.md) | Coursera / Udemy / YouTube / Microsoft cert links |

### Flow understanding

| Document | Description |
|----------|-------------|
| [interview-prep/flow-understanding/README.md](interview-prep/flow-understanding/README.md) | End-to-end system map (UI → API → MAF → MCP) |
| [interview-prep/flow-understanding/components-cheatsheet.md](interview-prep/flow-understanding/components-cheatsheet.md) | Ports, processes, and what each folder owns |
| [interview-prep/flow-understanding/function-by-function-debug.md](interview-prep/flow-understanding/function-by-function-debug.md) | Follow a request through functions |
| [interview-prep/flow-understanding/adding-a-new-flow.md](interview-prep/flow-understanding/adding-a-new-flow.md) | Checklist to add another agent/flow |
| [interview-prep/flow-understanding/azure-sql-blob.md](interview-prep/flow-understanding/azure-sql-blob.md) | Azure SQL + Blob as used in this stack |

### FastAPI / LangChain / LangGraph

| Document | Description |
|----------|-------------|
| [interview-prep/fastapi-basic/README.md](interview-prep/fastapi-basic/README.md) | FastAPI patterns used by `ip_api` and MAF |
| [interview-prep/langchain-basic/README.md](interview-prep/langchain-basic/README.md) | LangChain study order for this repo |
| [interview-prep/langchain-basic/01-core-building-blocks.md](interview-prep/langchain-basic/01-core-building-blocks.md) | Messages, chat models, prompts, parsers |
| [interview-prep/langchain-basic/02-lcel-chains.md](interview-prep/langchain-basic/02-lcel-chains.md) | LCEL pipelines (`\|`, invoke / stream / batch) |
| [interview-prep/langchain-basic/03-rag-with-langchain.md](interview-prep/langchain-basic/03-rag-with-langchain.md) | RAG flow (this repo does not ship Chroma) |
| [interview-prep/langchain-basic/04-agents-tools-memory.md](interview-prep/langchain-basic/04-agents-tools-memory.md) | Tools, agents, memory vs LangGraph |
| [interview-prep/langchain-basic/05-this-repo-how-we-use-langchain.md](interview-prep/langchain-basic/05-this-repo-how-we-use-langchain.md) | Mapper / validator / voice LCEL in this project |
| [interview-prep/langchain-basic/06-interview-qa.md](interview-prep/langchain-basic/06-interview-qa.md) | LangChain interview Q&A |
| [interview-prep/langgraph-basic/README.md](interview-prep/langgraph-basic/README.md) | LangGraph study order |
| [interview-prep/langgraph-basic/01-core-concepts.md](interview-prep/langgraph-basic/01-core-concepts.md) | State, nodes, edges, compile |
| [interview-prep/langgraph-basic/02-document-graph-code.md](interview-prep/langgraph-basic/02-document-graph-code.md) | Document pipeline graph in this repo |
| [interview-prep/langgraph-basic/03-voice-graph-hitl-memory.md](interview-prep/langgraph-basic/03-voice-graph-hitl-memory.md) | Voice graph + interrupt / HITL |
| [interview-prep/langgraph-basic/04-memory-management.md](interview-prep/langgraph-basic/04-memory-management.md) | Checkpointers and thread ids |
| [interview-prep/langgraph-basic/05-interview-qa.md](interview-prep/langgraph-basic/05-interview-qa.md) | LangGraph interview Q&A |

### MAF / MCP / memory / Q&A

| Document | Description |
|----------|-------------|
| [interview-prep/maf-basic/README.md](interview-prep/maf-basic/README.md) | Microsoft Agent Framework study order |
| [interview-prep/maf-basic/01-what-is-maf.md](interview-prep/maf-basic/01-what-is-maf.md) | What MAF is vs LangGraph |
| [interview-prep/maf-basic/02-agent-mcp-code.md](interview-prep/maf-basic/02-agent-mcp-code.md) | How this repo’s MAF calls MCP |
| [interview-prep/maf-basic/03-architecture-in-this-repo.md](interview-prep/maf-basic/03-architecture-in-this-repo.md) | MAF placement in the five-process stack |
| [interview-prep/maf-basic/04-memory-and-sessions.md](interview-prep/maf-basic/04-memory-and-sessions.md) | Session ids vs graph checkpoints |
| [interview-prep/maf-basic/05-interview-qa.md](interview-prep/maf-basic/05-interview-qa.md) | MAF interview Q&A |
| [interview-prep/maf-basic/06-tool-calling-and-hallucination.md](interview-prep/maf-basic/06-tool-calling-and-hallucination.md) | Tool calling and reducing invented tools |
| [interview-prep/maf-basic/07-azure-foundry-deploy-and-auth.md](interview-prep/maf-basic/07-azure-foundry-deploy-and-auth.md) | Foundry deploy and auth notes |
| [interview-prep/maf-basic/08-session-context-architecture-changes.md](interview-prep/maf-basic/08-session-context-architecture-changes.md) | Proposed session-context changes |
| [interview-prep/mcp-basic/README.md](interview-prep/mcp-basic/README.md) | MCP / FastMCP study notes |
| [interview-prep/mcp-basic/02-fastmcp-mlflow-docs-validity.md](interview-prep/mcp-basic/02-fastmcp-mlflow-docs-validity.md) | FastMCP docs vs MLflow add-on validity |
| [interview-prep/mcp-basic/ml-flow-implementation-report.md](interview-prep/mcp-basic/ml-flow-implementation-report.md) | MLflow notes (not a runtime dependency here) |
| [interview-prep/memory/README.md](interview-prep/memory/README.md) | Memory types across API sessions and graphs |
| [interview-prep/r_n_d/use-case/langgraph-maf-memory-types.md](interview-prep/r_n_d/use-case/langgraph-maf-memory-types.md) | R&D: LangGraph vs MAF memory |
| [interview-prep/what-happen-in-this-code/README.md](interview-prep/what-happen-in-this-code/README.md) | Walk real code paths for interviews |
| [interview-prep/qa-bank/README.md](interview-prep/qa-bank/README.md) | Spoken-answer question bank |
| [interview-prep/qa-bank/glossary.md](interview-prep/qa-bank/glossary.md) | Short glossary (MCP, MAF, HITL, xid, …) |
