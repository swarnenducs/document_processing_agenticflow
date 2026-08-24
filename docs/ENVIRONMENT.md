# Environment variables

Copy [`.env.example`](../.env.example) to `.env` at the repo root for `python run_all_components.py`. Each package also has its own `.env.example` for a standalone run. A component `.env` is loaded first; the **root** `.env` fills keys the folder file does not set.

**Never commit `.env`**, Azure keys, SAS tokens, Foundry endpoints, or toolbox URLs.

Related: [LOCAL_AND_CLOUD_STORAGE.md](LOCAL_AND_CLOUD_STORAGE.md), [DOCUMENT_LLM_OPTIMIZATION.md](DOCUMENT_LLM_OPTIMIZATION.md), [function-by-function-debug.md](interview-prep/flow-understanding/function-by-function-debug.md).

---

## Which process reads which file

| Component | Port | Standalone template | Role |
|---|---|---|---|
| **UI** | `:7860` | [`UI/.env.example`](../UI/.env.example) | Gradio. HTTP client only — no SQL, Blob, or LLM keys |
| **ip_api** | `:8000` | [`ip_api/.env.example`](../ip_api/.env.example) | FastAPI gateway, jobs, admin templates, speech, proxies to MAF |
| **document-mcp** | `:8001` | [`document-processing-mcp/.env.example`](../document-processing-mcp/.env.example) | Word LangGraph: mapper + critics |
| **voice-mcp** | `:8002` | [`voice_enable_mcp/.env.example`](../voice_enable_mcp/.env.example) | Voice → contract HITL LangGraph |
| **MAF** | `:8003` | [`central-agentic-flow/.env.example`](../central-agentic-flow/.env.example) | Chat orchestrator; jobs via `POST /invoke` |
| **All (local stack)** | — | [root `.env.example`](../.env.example) | Shared keys + one section per process |

In the tables below, **Belongs to** is the process that *uses* the variable. Shared storage keys are read by every SQL-using process (not the UI).

---

## Debug flow (default off)

Put these in the **root** `.env` so every child process inherits them, or in a single component `.env` to log only that process. Restart after changing.

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `DEBUG_FLOW` | unset (off) | **All five processes** | `1` / `true` / `trace` = print `file:line method` for every project function. `hops` = only named hops already in code. `break` = hops + debugger pause |
| `DEBUG_FLOW_POINTS` | unset | **All five** | Comma-separated hop or function names (`create_document_job,map_fields_node`). Restricts `DEBUG_FLOW=1` or `hops` |
| `DEBUG_FLOW_BREAK` | unset (off) | **All five** | `1` = also `breakpoint()` at matching hops (start the process under F5) |

CLI equivalent: `python run_all_components.py --debug-flow` sets `DEBUG_FLOW=1` if it is not already set.

Example:

```bash
DEBUG_FLOW=1
# DEBUG_FLOW=hops
# DEBUG_FLOW_POINTS=create_document_job,map_fields_node,ask_maf
# DEBUG_FLOW_BREAK=1
```

---

## Shared provider keys

Used by whichever process actually calls that provider. UI never needs these.

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `OPENAI_API_KEY` | empty | document-mcp, voice-mcp, MAF, ip_api (health/speech) | OpenAI API key |
| `OPENAI_MODEL` | unset | LLM callers | Optional default OpenAI model name |
| `OPENAI_BASE_URL` | unset | LLM callers | Custom OpenAI-compatible base URL |
| `AZURE_OPENAI_API_KEY` | empty | document-mcp, voice-mcp, MAF, ip_api | Azure OpenAI key |
| `AZURE_OPENAI_ENDPOINT` | empty | same | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` | same | Azure OpenAI API version |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-5-mini` | document-mcp, voice-mcp, MAF | Default Azure deployment (mapper / MAF) |
| `AZURE_OPENAI_VALIDATOR_DEPLOYMENT` | `gpt-4.1-mini` | document-mcp | Azure deployment for the judge / extraction critic |
| `GROQ_API_KEY` | empty | document-mcp, ip_api (speech), voice-mcp, MAF | Groq key |
| `GROQ_VALIDATOR_MODEL` | unset | document-mcp | Groq model id if the validator uses Groq |
| `GROQ_MODEL` | unset | LLM callers | Optional Groq chat model |
| `GROQ_BASE_URL` | unset | LLM callers | Custom Groq base URL |
| `ANTHROPIC_API_KEY` | unset | LLM callers | Optional Anthropic |
| `GOOGLE_API_KEY` | unset | LLM callers | Optional Google |
| `MISTRAL_API_KEY` | unset | LLM callers | Optional Mistral |
| `COMPATIBLE_BASE_URL` | unset | document-mcp | OpenAI-compatible server (Ollama, vLLM, …) |
| `COMPATIBLE_API_KEY` | unset | document-mcp | Key for that compatible server |
| `OLLAMA_BASE_URL` | unset | document-mcp | Local Ollama (`http://127.0.0.1:11434`) |

---

## Shared storage (not UI)

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `STORAGE_BASE_PATH` | `./data/storage` | ip_api, document-mcp, voice-mcp, MAF | Root for jobs, audio, templates, scratch |
| `SQLITE_DATABASE_PATH` | `./data/app.db` | same | SQLite file when Azure SQL is unset |
| `JOBS_SUBDIRECTORY` | `jobs` | ip_api, document-mcp | Folder / blob prefix segment for jobs |
| `AUDIO_SUBDIRECTORY` | `audio` | ip_api, voice-mcp | Audio upload folder |
| `TEMPLATES_SUBDIRECTORY` | `templates` | ip_api | Local admin template library |
| `JOB_TTL_HOURS` | `24` | ip_api | How long job artifacts are kept |
| `MAX_UPLOAD_MB` | `25` | ip_api, document-mcp, voice-mcp | Upload size cap |
| `FILE_STORAGE_BACKEND` | `local` (or `azure_blob` if blob creds exist) | ip_api, document-mcp | `local` or `azure_blob` |
| `SQLALCHEMY_DATABASE_URL` | unset | SQL users | Full DB URL; wins over `AZURE_SQL_*` |
| `AZURE_SQL_SERVER` | unset | SQL users | Azure SQL host; unset = SQLite |
| `AZURE_SQL_USER` | `adminsql` | SQL users | SQL login |
| `AZURE_SQL_PASSWORD` | unset | SQL users | SQL password (or leave empty and use Key Vault locally) |
| `AZURE_SQL_DATABASE` | `ipp-app-db` | SQL users | Database name |
| `AZURE_SQL_DIALECT` | `pyodbc` | SQL users | `pyodbc` or `pymssql` |
| `AZURE_SQL_ODBC_DRIVER` | `ODBC Driver 18 for SQL Server` | SQL users | ODBC driver name |
| `AZURE_KEY_VAULT_NAME` | unset | **local scripts / `run_all_components.py`** | Vault name; fetch SQL password via `az` |
| `AZURE_KEY_VAULT_URL` | unset | local scripts | Alternate to vault name |
| `AZURE_SQL_PASSWORD_SECRET_NAME` | `azure-sql-password` | local scripts | Secret name in the vault |
| `AZURE_BLOB_CONTAINER` | `docuploadsolution` | ip_api, document-mcp | Blob container |
| `AZURE_BLOB_PREFIX` | `jobs` | ip_api, document-mcp | Blob prefix for job files |
| `AZURE_BLOB_TEMPLATE_PREFIX` | `templates` | ip_api | Blob prefix for the template library |
| `AZURE_STORAGE_CONNECTION_STRING` | unset | ip_api, document-mcp | One-string blob auth |
| `AZURE_STORAGE_ACCOUNT_NAME` | unset | ip_api, document-mcp | Account name (with key or SAS) |
| `AZURE_STORAGE_ACCOUNT_KEY` | unset | ip_api, document-mcp | Account key |
| `AZURE_STORAGE_SAS_TOKEN` | unset | ip_api, document-mcp | SAS token (preferred over key if both set) |
| `AZURE_STORAGE_SAS_URL` | unset | ip_api, document-mcp | Full SAS URL |
| `TRACE_LOGGING_ENABLED` | `true` | ip_api, document-mcp, voice-mcp, MAF | Persist call/trace rows |
| `TRACE_LOG_MAX_CHARS` | `16000` | same | Cap stored request/response text |

---

## UI (`:7860`)

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `GRADIO_HOST` | `127.0.0.1` | UI | Bind address |
| `GRADIO_PORT` | `7860` | UI | Bind port |
| `API_BASE_URL` | `http://127.0.0.1:8000` | UI (and ip_api health links) | FastAPI base the Gradio client calls |
| `DEBUG_FLOW` | off | UI | Same as [debug flow](#debug-flow-default-off); logs Gradio + `api_client` |

---

## ip_api (`:8000`)

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `API_HOST` | `0.0.0.0` | ip_api | Bind address |
| `API_PORT` | `8000` | ip_api | Bind port |
| `ADMIN_API_KEY` | empty (admin off) | ip_api | `X-Admin-Api-Key` for `/api/v1/admin/templates` |
| `MAF_BASE_URL` | `http://127.0.0.1:8003` | ip_api | MAF URL for `/api/ask` and `/invoke` |
| `MAF_PROXY_TIMEOUT` | `320` | ip_api | Seconds for the MAF HTTP proxy |
| `DOCUMENT_MCP_URL` | `http://127.0.0.1:8001/mcp` | ip_api | Document MCP (health / catalog; jobs go MAF → MCP) |
| `VOICE_MCP_URL` | `http://127.0.0.1:8002/mcp` | ip_api | Voice MCP URL |
| `SPEECH_PROVIDER` | `groq` | ip_api | `groq` / `openai` / `azure_openai` / `auto` for `POST /audio/transcribe` |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3` | ip_api, voice-mcp | Groq STT model |
| `OPENAI_WHISPER_MODEL` | `whisper-1` | ip_api, voice-mcp | OpenAI STT model |
| `AZURE_OPENAI_WHISPER_DEPLOYMENT` | unset | ip_api, voice-mcp | Azure Whisper deployment name |
| `DOCUMENT_MAX_RETRIES` | `1` | ip_api (passed to MCP), document-mcp | Default judge retries when the form omits `max_retries` (0–3) |
| `DOCUMENT_VALIDATION_THRESHOLD` | `0.7` | ip_api, document-mcp | Default judge score bar when the form omits it (0–1) |
| `DOCUMENT_ACCURACY_THRESHOLD` | alias | same | Alias for `DOCUMENT_VALIDATION_THRESHOLD` |
| `VALIDATION_THRESHOLD` | alias | same | Alias for `DOCUMENT_VALIDATION_THRESHOLD` |
| `MAX_RETRIES` | alias | same | Alias for `DOCUMENT_MAX_RETRIES` |
| `DOCUMENT_LLM_OPTIMIZATION_ENABLED` | `false` | ip_api, document-mcp | Default for `optimized_flow` when the request omits it |
| `DOCUMENT_LLM_ROUTING_ENABLED` | alias | same | Alias for `DOCUMENT_LLM_OPTIMIZATION_ENABLED` |
| `MAPPER_MODEL_ID` / `MAPPER_PROVIDER` / `MAPPER_MODEL` | see document-mcp | ip_api (health banner only) | Shown on `/health`; the mapper runs inside document-mcp |
| `VALIDATOR_MODEL_ID` / `VALIDATOR_PROVIDER` / `VALIDATOR_MODEL` | see document-mcp | ip_api (health banner only) | Same for the judge |

---

## document-processing-mcp (`:8001`)

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `DOCUMENT_MCP_HOST` | `127.0.0.1` | document-mcp | Bind address |
| `DOCUMENT_MCP_PORT` | `8001` | document-mcp | Bind port |
| `DOCUMENT_MCP_TRANSPORT` | `http` | document-mcp | `http` or `stdio` |
| `MCP_HOST` / `MCP_PORT` / `MCP_TRANSPORT` | aliases | document-mcp | Older aliases for the bind/transport |
| `DOCUMENT_PROMPTS_DIR` | `./prompts` | document-mcp | Mapper / validator YAML folder |
| `MAPPER_MODEL_ID` | `openai:gpt-5-mini` | document-mcp, voice-mcp | LangChain `provider:model` for LLM #1 (mapper) |
| `MAPPER_PROVIDER` | `openai` | document-mcp | Split provider if `MAPPER_MODEL_ID` is unset |
| `MAPPER_MODEL` | `gpt-5-mini` | document-mcp | Split model name |
| `MAPPER_API_KEY` | unset | document-mcp | Override key for the mapper only |
| `MAPPER_BASE_URL` | unset | document-mcp | Override mapper base URL |
| `MAPPER_API_VERSION` | unset | document-mcp | Azure API version for the mapper |
| `MAPPER_TEMPERATURE` | `0` | document-mcp | Mapper temperature |
| `MAPPER_MAX_TOKENS` | unset | document-mcp | Mapper completion cap |
| `VALIDATOR_MODEL_ID` | `openai:gpt-4.1-mini` | document-mcp | LLM #2 (judge + extraction critic) |
| `VALIDATOR_PROVIDER` | `openai` | document-mcp | Split provider for the judge |
| `VALIDATOR_MODEL` | `gpt-4.1-mini` | document-mcp | Split model name |
| `VALIDATOR_MAX_TOKENS` | `1024` | document-mcp | Judge / critic completion cap |
| `LLM_MAX_TOKENS` | unset | document-mcp | Fallback completion cap |
| `DOCUMENT_MAX_RETRIES` | `1` | document-mcp | Env default retries when optimised flow is **off** and the request omits `max_retries` |
| `DOCUMENT_VALIDATION_THRESHOLD` | `0.7` | document-mcp | Env default judge bar when optimised flow is off |
| `DOCUMENT_LLM_OPTIMIZATION_ENABLED` | `false` | document-mcp | Turn on JSON mapper cascade for all jobs unless the request sets `optimized_flow=false` |
| `DOCUMENT_LLM_OPTIMIZATION_CONFIG` | `document-processing-mcp/config/llm_optimization.json` | document-mcp | Path to the optimisation JSON (read only when the flow is on) |
| `DOCUMENT_LLM_ROUTING_CONFIG` | alias | document-mcp | Alias for `DOCUMENT_LLM_OPTIMIZATION_CONFIG` |
| `AGENT_MODEL_ID` / `AGENT_PROVIDER` / `AGENT_MODEL` / `AGENT_MAX_TOKENS` | unset | document-mcp | Optional extra agent role (not the default pipeline) |

When **optimised flow is on** and the request omits retries/threshold, values come from `llm_optimization.json`, not from `DOCUMENT_MAX_RETRIES`.

---

## voice_enable_mcp (`:8002`)

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `VOICE_MCP_HOST` | `127.0.0.1` | voice-mcp | Bind address |
| `VOICE_MCP_PORT` | `8002` | voice-mcp | Bind port |
| `VOICE_MCP_TRANSPORT` | `http` | voice-mcp | `http` or `stdio` |
| `VOICE_PROMPTS_DIR` | `./prompts` | voice-mcp | Intent / confirm YAML |
| `MAPPER_MODEL_ID` | `openai:gpt-5-mini` | voice-mcp | Intent + confirm LLM (same mapper credentials as documents if you share keys) |
| `MAPPER_PROVIDER` | `openai` | voice-mcp | Split provider |
| `AGENT_MODEL_ID` | unset | voice-mcp | Optional override for the contract agent |
| `SPEECH_PROVIDER` | `groq` | voice-mcp | STT if audio is sent to this MCP |
| `LANGGRAPH_CHECKPOINT_BACKEND` | `sql` | voice-mcp | HITL interrupt store: `sql` (same SQLite / Azure SQL) or `redis` |
| `REDIS_URL` | unset | voice-mcp | Redis URL when the checkpointer is `redis` |
| `LANGGRAPH_CHECKPOINT_REDIS_PREFIX` | `lg` | voice-mcp | Redis key prefix |
| `LANGGRAPH_CHECKPOINT_REDIS_TTL_SECONDS` | `86400` | voice-mcp | Redis TTL for checkpoints |

---

## central-agentic-flow MAF (`:8003`)

| Variable | Default | Belongs to | What it does |
|---|---|---|---|
| `MAF_HOST` | `0.0.0.0` | MAF | Bind address |
| `MAF_PORT` | `8003` | MAF | Bind port |
| `MAF_MCP_TIMEOUT_SECONDS` | `300` | MAF | Timeout talking to MCP tools |
| `MAF_MODEL_ID` | `openai:gpt-5-mini` | MAF | Chat model for `POST /ask` only (jobs use `/invoke`, no chat model) |
| `MAF_PROVIDER` | `openai` | MAF | Split provider |
| `MAF_MODEL` | `gpt-5-mini` | MAF | Split model name |
| `MAF_API_KEY` | unset | MAF | Override key for the orchestrator |
| `MAF_LLM_BASE_URL` | unset | MAF | Override base URL |
| `MAF_API_VERSION` | unset | MAF | Azure API version for MAF |
| `MAF_INSTRUCTIONS` | unset | MAF | Inline orchestrator instructions |
| `MAF_INSTRUCTIONS_FILE` | prompts file | MAF | Path to orchestrator markdown |
| `MAF_PROMPTS_DIR` | `./prompts` | MAF | Prompt folder |
| `MAF_MCP_REGISTRY_FILE` | `./config/mcp_registry.yml` | MAF | MCP catalog YAML |
| `DOCUMENT_MCP_URL` | `http://127.0.0.1:8001/mcp` | MAF | Document MCP (jobs-only in the registry) |
| `VOICE_MCP_URL` | `http://127.0.0.1:8002/mcp` | MAF | Voice MCP (jobs-only in the registry) |
| `BUSINESS_MCP_URL` | unset | MAF | Optional chat-mode business MCP |
| `MAF_EXTRA_MCPS` | unset | MAF | Extra MCPs, `name=url,name=url` |
| `MAF_MCP_FABRIC_DESCRIPTION` | unset | MAF | Description for a Fabric extra MCP |
| `FABRIC_SQL_AGENT_URL` | unset | MAF | Fabric SQL agent URL |
| `MAF_MCP_SERVERS` | unset | MAF | JSON list of extra MCP servers |
| `FOUNDRY_PROJECT_ENDPOINT` | unset | MAF (Foundry host) | Foundry project endpoint — **do not commit** |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | unset | MAF (Foundry) | Hosted chat deployment name |
| `TOOLBOX_ENDPOINT` | unset | MAF (Foundry) | Foundry Toolbox MCP URL — **do not commit** |
| `FOUNDRY_MAF_INSTRUCTIONS` | unset | MAF (Foundry) | Instructions for the hosted chat agent |

---

## Quick “where do I set this?”

| I want to… | Set | On |
|---|---|---|
| See `file:line method` while debugging | `DEBUG_FLOW=1` | root `.env` (all processes) or one component |
| Log only mapper / job hops | `DEBUG_FLOW=hops` + `DEBUG_FLOW_POINTS=…` | same |
| Pause in the IDE at hops | `DEBUG_FLOW_BREAK=1` | same + F5 |
| Use the cheaper mapper cascade | `DOCUMENT_LLM_OPTIMIZATION_ENABLED=true` | ip_api **and** document-mcp (or root `.env`) |
| Point at a custom optimisation JSON | `DOCUMENT_LLM_OPTIMIZATION_CONFIG` | document-mcp |
| Change default judge retries | `DOCUMENT_MAX_RETRIES` | ip_api + document-mcp |
| Talk to Azure SQL | `AZURE_SQL_*` (password via vault locally) | all SQL processes |
| Store .docx in Blob | `FILE_STORAGE_BACKEND=azure_blob` + storage creds | ip_api + document-mcp |
| Enable admin templates | `ADMIN_API_KEY` | ip_api |
| Point the UI at another API | `API_BASE_URL` | UI |
| Change STT | `SPEECH_PROVIDER` | ip_api (and voice-mcp if it transcribes) |
