# 07 — Deploy MAF on Azure AI Foundry + Microsoft auth

How this local **central-agentic-flow (MAF)** maps to **Azure AI Foundry**, and how Microsoft identity is used.

> Local today: MAF runs as a FastAPI service (`:8003`) with `Agent` + `MCPStreamableHTTPTool` against your MCP URLs.  
> On Foundry: same *role* (orchestrator agent + tools), hosted as a **Foundry agent** (prompt or **hosted** container) talking to models and optional MCP/OpenAPI tools.

## Two deployment shapes

### A) Foundry-hosted agent (recommended product path)

```text
Users / App
  → Microsoft Entra ID (auth)
  → Your API or Foundry Agents API
  → Foundry Agent (instructions ≈ orchestrator_instructions.md)
        ├─ Model deployment (Azure OpenAI in the Foundry project)
        └─ Tools: MCP / OpenAPI / functions → your document & voice backends
```

**Steps (conceptual):**

1. **Create Foundry resource + project** (Portal, or `az` / Foundry project workflows).
2. **Deploy a chat model** in the project (e.g. `gpt-4o` / `gpt-4o-mini`) with enough quota in the region.
3. **Create an agent** whose system instructions are copied from  
   `central-agentic-flow/prompts/orchestrator_instructions.md`.
4. **Register tools** that reach your MCP capabilities:
   - Prefer exposing stable **HTTPS** MCP or REST wrappers (your `ip_api` `/api/v1/agents/*` or MCP streamable HTTP behind App Service / ACA / APIM).
   - Map the same operations: `generate_document`, `start_voice_contract`, `confirm_voice_contract`, …
5. **Host backends**: containerize `document-processing-mcp`, `voice_enable_mcp`, and optionally keep a thin gateway — same Dockerfiles as local compose.
6. **Smoke-test** via Foundry playground / Agents invoke API, then wire Gradio or your app to that endpoint instead of `http://127.0.0.1:8003`.

**Hosted agent variant:** package the Python agent (Agent Framework code similar to `orchestrator.py`) as a **hosted** Foundry agent image (`azd` / Foundry deploy). Connections for model + MCP URLs are injected as env (same idea as `MAF_PROVIDER`, `DOCUMENT_MCP_URL`, `VOICE_MCP_URL`).

### B) Keep MAF as your container; only use Foundry for the model

```text
UI → ip_api → central-agentic-flow (ACA / App Service)
                  │
                  ├─ MAF_PROVIDER=azure_openai
                  ├─ AZURE_OPENAI_ENDPOINT + deployment (Foundry/AOAI)
                  └─ DOCUMENT_MCP_URL / VOICE_MCP_URL → other containers
```

This matches **current code** (`resolve_maf_chat_client()` azure branch) with minimal refactor: deploy existing images, point LLM env at the Foundry/Azure OpenAI deployment.

| Env (local → Azure) | Purpose |
|---|---|
| `MAF_PROVIDER=azure` / `azure_openai` | Use Azure OpenAI-compatible client |
| `AZURE_OPENAI_ENDPOINT` / `MAF_LLM_BASE_URL` | Foundry / AOAI endpoint |
| `AZURE_OPENAI_API_KEY` or **Entra** token | Auth to the model |
| `AZURE_OPENAI_DEPLOYMENT` / `MAF_MODEL` | Deployment name |
| `DOCUMENT_MCP_URL`, `VOICE_MCP_URL` | Internal HTTPS to MCP services |

## Microsoft authentication (what to use where)

```text
┌─────────────────┐     Entra ID      ┌──────────────────┐
│ User / SPA / UI │ ─── Bearer JWT ──► │ Your API (ip_api)│
└─────────────────┘                    └────────┬─────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    ▼                           ▼                           ▼
            Call Foundry Agents         Call Azure OpenAI            Call MCP backends
            (agent run)                 (orchestrator LLM)           (managed identity)
```

### 1. User → your app (interactive)

- Register an **App registration** in **Microsoft Entra ID**.
- Gradio/SPA uses MSAL (auth code + PKCE) or your org’s gateway.
- API validates JWT (`aud`, `iss`, roles/scopes like `access_as_user`).
- Do **not** put Azure OpenAI keys in the browser.

### 2. App → Azure OpenAI / Foundry model (service)

Prefer **passwordless**:

| Mechanism | When |
|---|---|
| **Managed Identity** on ACA/App Service + RBAC on Foundry/Cognitive Services | Production default |
| **Service principal** (client id/secret or cert) | CI/CD, local automation |
| API key | Dev only; rotate via Key Vault |

Assign Foundry / Cognitive Services roles as needed (e.g. **Cognitive Services OpenAI User** for invoke; Foundry project roles for agent authoring — see Foundry RBAC docs).

Local code today often uses `AZURE_OPENAI_API_KEY`. On Azure, replace with DefaultAzureCredential / managed identity in the chat client configuration.

### 3. App → MCP tools (service-to-service)

- Put MCPs on a **private network** (VNet / private endpoints).
- Authenticate with **managed identity** or APIM subscription keys / mTLS.
- MAF (or Foundry agent) calls only those authenticated endpoints — users never hit MCP directly.

### 4. App → Foundry Agents API

- Same Entra app or a backend MI obtains a token for the Foundry / Azure AI scope.
- RBAC: Foundry User / Project Manager / Owner depending on whether the identity only **invokes** or also **creates** agents.

## Minimal security baseline for interviews

1. **Entra ID** for users; no shared passwords in UI.
2. **Managed identity** from orchestrator container → model + tools.
3. **Key Vault** if any secrets remain.
4. **Network isolation** for MCP (not public anonymous).
5. **HITL + tool grounding** still apply in cloud (hallucination doc).
6. **RAI / content filters** on the Azure OpenAI deployment.

## Mapping this repo → Foundry checklist

| Local artifact | Foundry / Azure |
|---|---|
| `orchestrator_instructions.md` | Agent instructions |
| `MCPStreamableHTTPTool` URLs | Foundry tool connections / private MCP endpoints |
| `MAF_MODEL` + Azure env | Project model deployment |
| `POST /api/ask` | Agents invoke API **or** your container still exposes `/ask` |
| Gradio Central Agent tab | Same UX → Foundry/backend URL |
| `GET /api/v1/agents/tools` | Keep for ops UI; or Foundry tool list in portal |

## Useful commands (orientation)

```bash
# After az login — inspect subscription / account (examples)
az account show
az cognitiveservices account list -o table

# Local still works against Azure-hosted model:
# MAF_PROVIDER=azure_openai
# AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
# AZURE_OPENAI_API_KEY=...   # or MI in cloud
# MAF_MODEL=<deployment-name>
```

For full Foundry agent lifecycle (scaffold, `azd` deploy, eval, RBAC), use Microsoft Foundry project workflows / Portal **Agents** blade; keep this doc as the **repo-specific** mapping.

Back: [06-tool-calling-and-hallucination.md](06-tool-calling-and-hallucination.md) · [README.md](README.md)
