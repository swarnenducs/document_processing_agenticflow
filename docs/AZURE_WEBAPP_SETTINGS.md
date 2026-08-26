# Azure Web App settings — fill placeholders, then deploy

Each component has a Portal **Advanced edit** JSON file. Replace every `<angle-bracket>` token (and Key Vault secret names). Leave keys that already have real defaults (`WEBSITES_PORT`, `FILE_STORAGE_BACKEND=azure_blob`) unless you know you need to change them.

**Never put real passwords or API keys in git.** Use Key Vault references in the JSON (`@Microsoft.KeyVault(SecretUri=...)`).

How to paste: Azure Portal → Web App → **Environment variables** (or Configuration) → **Advanced edit** → paste the file. That format is `{ "name", "value", "slotSetting" }[]`. It is **not** `az webapp config appsettings set --settings @file.json`.

Related: [DYNACONF.md](DYNACONF.md), [ENVIRONMENT.md](ENVIRONMENT.md), [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

Replace these tokens in **every** file you use:

| Token | Fill with |
|-------|-----------|
| `<vault-name>` | Key Vault name (SQL password secret default: `azure-sql-password`) |
| `<sql-server>` | Azure SQL host without `tcp:` |
| `<api-app>` | ip_api Web App hostname |
| `<maf-app>` | MAF Web App hostname |
| `<document-mcp-app>` | document MCP Web App hostname |
| `<voice-mcp-app>` | voice MCP Web App hostname |
| `<chat-mcp-app>` / `<metadata-mcp-app>` | optional extra MCP Web Apps — see [ADD_MAF_MCP_AGENTS.md](ADD_MAF_MCP_AGENTS.md) |
| `<azure-openai-resource>` | Azure OpenAI / AI Services resource |
| `<mapper-deployment>` / `<validator-deployment>` / `<maf-deployment>` | model deployment names |
| `<*-secret>` | Key Vault secret names you create |

Give each Web App **Key Vault Secrets User** on that vault (managed identity).

---

## UI (`:7860`)

File: [UI/config/azure-webapp.settings.json](../UI/config/azure-webapp.settings.json)

Startup (General settings):

```text
python -m ui_app.ui.gradio_app
```

**You must fill**

| Name | Example |
|------|---------|
| `API_BASE_URL` | `https://<api-app>.azurewebsites.net` |

UI has no SQL, Blob, or LLM keys.

---

## ip_api (`:8000`)

File: [ip_api/config/azure-webapp.settings.json](../ip_api/config/azure-webapp.settings.json)

Startup:

```text
python -m uvicorn ip_api.api.main:app --host 0.0.0.0 --port 8000
```

**You must fill**

| Name | Notes |
|------|--------|
| `API_BASE_URL` | This app’s HTTPS URL |
| `CENTRAL_AGENT_END_POINT` | `https://<maf-app>.azurewebsites.net` (no `/invoke` suffix). Wins over `MAF_BASE_URL` / `MAF_URL`. |
| `MAF_BASE_URL` | Alias of `CENTRAL_AGENT_END_POINT` (same value; optional if the preferred name is set) |
| `DOCUMENT_MCP_URL` | `https://<document-mcp-app>.azurewebsites.net/mcp` (health/catalog; jobs go MAF → MCP) |
| `VOICE_MCP_URL` | `https://<voice-mcp-app>.azurewebsites.net/mcp` |
| `AZURE_SQL_SERVER` | `<sql-server>.database.windows.net` |
| `AZURE_SQL_DATABASE` | real DB name (default placeholder `ipp-app-db`) |
| `AZURE_SQL_PASSWORD` | Key Vault ref (already in the file) |
| `AZURE_STORAGE_CONNECTION_STRING` | Key Vault ref, or use account name + key/SAS instead |
| `GROQ_API_KEY` / `OPENAI_API_KEY` / `AZURE_OPENAI_*` | STT; fill the provider you use (`SPEECH_PROVIDER`) |
| `ADMIN_API_KEY` | Key Vault ref if you lock admin template routes |
| `CORS_ORIGINS` | Comma-separated HTTPS origins for Angular (and Gradio UI). Example: `https://<angular-app>.azurewebsites.net` |

Keep `FILE_STORAGE_BACKEND=azure_blob` and do **not** set `SQLALCHEMY_DATABASE_URL` unless you intend to override Azure SQL parts.

---

## document-processing-mcp (`:8001`)

File: [document-processing-mcp/config/azure-webapp.settings.json](../document-processing-mcp/config/azure-webapp.settings.json)

Startup:

```text
python -m document_processing_mcp.server --transport http --host 0.0.0.0 --port 8001
```

**You must fill**

| Name | Notes |
|------|--------|
| `AZURE_SQL_SERVER` / `AZURE_SQL_DATABASE` / `AZURE_SQL_PASSWORD` | Same DB as ip_api |
| `AZURE_STORAGE_CONNECTION_STRING` | Same container as ip_api |
| `AZURE_OPENAI_ENDPOINT` + Key Vault `AZURE_OPENAI_API_KEY` | or OpenAI/Groq keys |
| `MAPPER_MODEL_ID` / `VALIDATOR_MODEL_ID` | e.g. `azure_openai:<deployment>` |
| `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_VALIDATOR_DEPLOYMENT` | if you split mapper vs validator |

No localhost MCP URLs. Jobs-only; chat must not call this app from Foundry `/ask`.

---

## voice_enable_mcp (`:8002`)

File: [voice_enable_mcp/config/azure-webapp.settings.json](../voice_enable_mcp/config/azure-webapp.settings.json)

Startup:

```text
python -m voice_enable_mcp.server --transport http --host 0.0.0.0 --port 8002
```

**You must fill**

| Name | Notes |
|------|--------|
| `AZURE_SQL_SERVER` / `AZURE_SQL_DATABASE` / `AZURE_SQL_PASSWORD` | Same DB as ip_api |
| Mapper / Azure OpenAI (or Groq/OpenAI) keys | voice LCEL parse |
| `GROQ_API_KEY` | if `SPEECH_PROVIDER=groq` (STT is usually in ip_api; keys still used if MCP parses with that provider) |
| `REDIS_URL` | only if `LANGGRAPH_CHECKPOINT_BACKEND=redis`; otherwise leave empty and keep `sql` |

---

## central-agentic-flow MAF (`:8003`)

File: [central-agentic-flow/config/azure-webapp.settings.json](../central-agentic-flow/config/azure-webapp.settings.json)

Startup (FastAPI Web App `/ask` + `/invoke`):

```text
python -m uvicorn central_agentic_flow.server:app --host 0.0.0.0 --port 8003
```

**You must fill**

| Name | Notes |
|------|--------|
| `TEMPLATE_PROCESSING_END_POINT` | HTTPS `/mcp` of document MCP — **not** localhost. Wins over `DOCUMENT_MCP_URL`. |
| `DOCUMENT_MCP_URL` | Alias of `TEMPLATE_PROCESSING_END_POINT` (same value; optional if the preferred name is set) |
| `VOICE_PROCESSING_END_POINT` | HTTPS `/mcp` of voice MCP. Wins over `VOICE_MCP_URL`. |
| `VOICE_MCP_URL` | Alias of `VOICE_PROCESSING_END_POINT` (same value; optional if the preferred name is set) |
| `MAF_MODEL_ID` | chat only, e.g. `azure_openai:<maf-deployment>` |
| `AZURE_OPENAI_ENDPOINT` + Key Vault API key | for `/ask` |
| `AZURE_SQL_*` | if this app writes traces to SQL |

Leave `BUSINESS_MCP_URL` empty unless you have an ask-mode business MCP.

Optional extra MCP slots (empty in the JSON until you have a Web App). Fill
HTTPS `/mcp` only — **not** localhost. Step-by-step:
[ADD_MAF_MCP_AGENTS.md](ADD_MAF_MCP_AGENTS.md).

| Name | Notes |
|------|--------|
| `CHAT_MCP_END_POINT` | Optional ask-mode chat MCP. Sibling of `BUSINESS_MCP_URL`. Wins over `CHAT_MCP_URL`. |
| `CHAT_MCP_URL` | Alias of `CHAT_MCP_END_POINT` |
| `METADATA_EXTRACTION_END_POINT` | Optional jobs-mode metadata MCP (`POST /invoke` only). Wins over `METADATA_MCP_URL`. |
| `METADATA_MCP_URL` | Alias of `METADATA_EXTRACTION_END_POINT` |

**Foundry hosted chat (optional, not this Web App `/invoke`):** fill `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_ENDPOINT` on the Foundry agent, not as localhost. Jobs still use this Web App `POST /invoke`. Chat MCP may go on the Toolbox; metadata must not.

---

## After you fill values

1. Create five Web Apps (or four if UI stays local).
2. Paste each JSON. Replace all `<...>`.
3. Set startup command + `WEBSITES_PORT` as above.
4. Grant the app identity **Key Vault Secrets User**.
5. Confirm SQL firewall allows Azure services / the app outbound.
6. Health: `GET https://<api-app>.azurewebsites.net/api/v1/health`

Local SQLite (not these JSON files): comment Azure SQL and vault vars in `.env` — see [ENVIRONMENT.md](ENVIRONMENT.md).
