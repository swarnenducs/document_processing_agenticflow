# Docs

**Full catalogue (every document + one-line description):** [INDEX.md](INDEX.md)

Runtime prompts stay next to each component (`central-agentic-flow/prompts/`, `document-processing-mcp/prompts/`, `voice_enable_mcp/prompts/`).

## Start here

| Doc | Topic |
|-----|--------|
| [INDEX.md](INDEX.md) | Complete index of all docs with short descriptions |
| [COMPONENTS.md](COMPONENTS.md) | Package layout and ports |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Architecture and interview talking points |
| [api-details-information.md](api-details-information.md) | HTTP / WebSocket / MCP API catalogue |
| [POSTMAN.md](POSTMAN.md) | Postman collection + local/Azure environments |
| [LOCAL_AND_CLOUD_STORAGE.md](LOCAL_AND_CLOUD_STORAGE.md) | SQLite/local files vs Azure SQL/Blob, admin templates |
| [ENVIRONMENT.md](ENVIRONMENT.md) | Env variables: what they do, which component, including `DEBUG_FLOW` |
| [DYNACONF.md](DYNACONF.md) | API, MAF, MCPs: Dynaconf + Pydantic BaseSettings (same env keys); Azure JSON; Key Vault |
| [TOKEN_CONSUMPTION.md](TOKEN_CONSUMPTION.md) | Estimated LLM tokens (and STT minutes) per component |
| [DOCUMENT_LLM_OPTIMIZATION.md](DOCUMENT_LLM_OPTIMIZATION.md) | Cheap vs strong mapper: complexity score + retry cascade (opt-in) |
| [VOICE_CONTRACT_FLOW.md](VOICE_CONTRACT_FLOW.md) | Voice → contract HITL flow |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Azure Web Apps + GitHub Actions |
| [ADD_MAF_MCP_AGENTS.md](ADD_MAF_MCP_AGENTS.md) | Optional chat (ask) and metadata (jobs) MCP slots on MAF |
| [interview-prep/](interview-prep/) | LangChain / LangGraph / MAF / MCP study notes |

Setup: [../README.md](../README.md). Windows install: [../install.ps1](../install.ps1).
