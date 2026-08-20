# Deploy MAF: Azure AI Foundry vs Azure Web Apps

This repo’s MAF is **`central-agentic-flow`**: FastAPI on **:8003** (`POST /ask`, `POST /invoke`). It uses **Microsoft Agent Framework in process** and calls document/voice **FastMCP HTTP** tools.

There are **two different Azure stories**. Do not mix them.

| | **A. Foundry = the LLM** (use this first) | **B. Foundry hosted agent** (not in this repo yet) |
|--|--|--|
| What you publish | Model deployment in Foundry / Azure OpenAI | The **agent container** inside Foundry |
| Where `/ask` runs | **Your** Web App (`central-agentic-flow`) | Foundry-hosted runtime (`agent.yaml` / `azd`) |
| MCP tools | MAF Web App calls `https://…:8001/mcp` and `:8002/mcp` | Hosted agent must reach those URLs (or Foundry MCP connections) |
| Code today | **Ready** — set `MAF_MODEL_ID=azure_openai:…` + Foundry endpoint | **Not ready** — see TODOs in this file and the chat |

---

## 1. Deploy the MAF **model** on Azure AI Foundry (step by step)

Goal: Foundry hosts GPT; **`central-agentic-flow` still runs as an app** and talks to that model.

### 1.1 Create Foundry project + model

1. Azure Portal → **Microsoft Foundry** (or Azure AI Foundry) → create / open a **project**.
2. In the project, **Models + endpoints** → **Deploy model**.
3. Pick a chat model (e.g. `gpt-4o-mini` / `gpt-4.1-mini`) → deploy. Wait until **Succeeded**.
4. Open the deployment → copy:
   - **Target URI** / endpoint (often `https://<resource>.cognitiveservices.azure.com` or `https://<resource>.services.ai.azure.com`)
   - **Key** (or use Entra later — keys work today)
   - **Deployment name** (this is the **model** string in env, not the display name)

### 1.2 Point MAF at Foundry (local or Web App)

In `.env` / App Settings for **central-agentic-flow** (and root `.env` if you use `run_all_components.py`):

```bash
MAF_MODEL_ID=azure_openai:YOUR_DEPLOYMENT_NAME
MAF_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2024-12-01-preview
# If the portal shows Foundry v1 (...services.ai.azure.com), this is enough:
# AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com
# Code appends /openai/v1 automatically.
```

`MAF_BASE_URL` is **not** the Foundry URL. That is the **MAF HTTP service** (`http://127.0.0.1:8003` or `https://doc-maf-….azurewebsites.net`). The LLM URL is `AZURE_OPENAI_ENDPOINT` / `MAF_LLM_BASE_URL`.

### 1.3 MCP URLs (required)

Foundry does **not** run your LangGraph. Document and voice MCP must already be reachable:

```bash
DOCUMENT_MCP_URL=https://doc-mcp-….azurewebsites.net/mcp
VOICE_MCP_URL=https://voice-mcp-….azurewebsites.net/mcp
```

Local: keep `http://127.0.0.1:8001/mcp` and `:8002/mcp`.

### 1.4 Smoke test

```bash
# MAF process running
curl -s http://127.0.0.1:8003/ask/health
curl -s http://127.0.0.1:8003/ask -H 'Content-Type: application/json' \
  -d '{"message":"health check — list tools if needed"}'
```

`/ask/health` builds `OpenAIChatClient` against Foundry and lists MCP tools.

### 1.5 Wire the API

ip_api:

```bash
MAF_BASE_URL=https://doc-maf-….azurewebsites.net
```

UI still talks only to ip_api (`API_BASE_URL`).

---

## 2. Deploy MAF (and the stack) as **Azure Web Apps** (step by step)

Goal: five Linux containers (or five Web Apps). Same Dockerfiles as `docker-compose.yml`.

Azure Web App = **one public HTTPS port**. MCP path is `/mcp` on the document/voice apps.

```text
Browser → UI Web App :443
            → API_BASE_URL → ip_api Web App
                 → MAF_BASE_URL → MAF Web App  POST /ask
                      → DOCUMENT_MCP_URL / VOICE_MCP_URL
```

### 2.1 Prerequisites

- `az login`, subscription, unique names
- Azure Container Registry (ACR)
- LLM keys (Foundry from §1, or OpenAI/Groq)
- Optional: Azure SQL + Blob (same env as local)

### 2.2 Resource group + plan + ACR

```bash
az login
az group create -n rg-doc-agent -l eastus

az appservice plan create -g rg-doc-agent -n plan-doc-agent --is-linux --sku B1

az acr create -g rg-doc-agent -n docagentacr$RANDOM --sku Basic
ACR=$(az acr show -g rg-doc-agent -n <ACR_NAME> --query loginServer -o tsv)
```

### 2.3 Build and push five images (from repo root)

```bash
az acr login -n <ACR_NAME>

docker build -t $ACR/document-mcp:latest ./document-processing-mcp
docker build -t $ACR/voice-mcp:latest ./voice_enable_mcp
docker build -t $ACR/maf:latest ./central-agentic-flow
docker build -t $ACR/ip-api:latest ./ip_api
docker build -t $ACR/ui:latest ./UI

docker push $ACR/document-mcp:latest
docker push $ACR/voice-mcp:latest
docker push $ACR/maf:latest
docker push $ACR/ip-api:latest
docker push $ACR/ui:latest
```

### 2.4 Create five Web Apps

```bash
for name in doc-mcp-dev voice-mcp-dev doc-maf-dev doc-api-dev doc-ui-dev; do
  az webapp create -g rg-doc-agent -p plan-doc-agent -n $name \
    --deployment-container-image-name nginx
done

az webapp config container set -g rg-doc-agent -n doc-mcp-dev \
  --docker-custom-image-name $ACR/document-mcp:latest --docker-registry-server-url https://$ACR
az webapp config container set -g rg-doc-agent -n voice-mcp-dev \
  --docker-custom-image-name $ACR/voice-mcp:latest --docker-registry-server-url https://$ACR
az webapp config container set -g rg-doc-agent -n doc-maf-dev \
  --docker-custom-image-name $ACR/maf:latest --docker-registry-server-url https://$ACR
az webapp config container set -g rg-doc-agent -n doc-api-dev \
  --docker-custom-image-name $ACR/ip-api:latest --docker-registry-server-url https://$ACR
az webapp config container set -g rg-doc-agent -n doc-ui-dev \
  --docker-custom-image-name $ACR/ui:latest --docker-registry-server-url https://$ACR
```

Enable ACR pull (admin user or managed identity). Set **WEBSITES_PORT** per app.

### 2.5 App settings (HTTPS URLs, not localhost)

Replace hostnames with yours.

**document MCP (`doc-mcp-dev`)**

```bash
az webapp config appsettings set -g rg-doc-agent -n doc-mcp-dev --settings \
  WEBSITES_PORT=8001 \
  DOCUMENT_MCP_HOST=0.0.0.0 \
  DOCUMENT_MCP_PORT=8001 \
  STORAGE_BASE_PATH=/home/data/storage \
  SQLITE_DATABASE_PATH=/home/data/app.db \
  FILE_STORAGE_BACKEND=azure_blob \
  AZURE_BLOB_CONTAINER=docuploadsolution \
  AZURE_STORAGE_CONNECTION_STRING='...' \
  AZURE_SQL_SERVER=... AZURE_SQL_PASSWORD=... AZURE_SQL_DATABASE=ipp-app-db
# plus MAPPER_* / VALIDATOR_* LLM keys
```

**voice MCP (`voice-mcp-dev`)** — `WEBSITES_PORT=8002`, `VOICE_MCP_HOST=0.0.0.0`, same SQL/blob/LLM as needed.

**MAF (`doc-maf-dev`)**

```bash
az webapp config appsettings set -g rg-doc-agent -n doc-maf-dev --settings \
  WEBSITES_PORT=8003 \
  MAF_HOST=0.0.0.0 \
  MAF_PORT=8003 \
  MAF_MODEL_ID=azure_openai:YOUR_DEPLOYMENT_NAME \
  AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.cognitiveservices.azure.com \
  AZURE_OPENAI_API_KEY=... \
  DOCUMENT_MCP_URL=https://doc-mcp-dev.azurewebsites.net/mcp \
  VOICE_MCP_URL=https://voice-mcp-dev.azurewebsites.net/mcp
```

**ip_api (`doc-api-dev`)**

```bash
az webapp config appsettings set -g rg-doc-agent -n doc-api-dev --settings \
  WEBSITES_PORT=8000 \
  API_HOST=0.0.0.0 \
  API_PORT=8000 \
  MAF_BASE_URL=https://doc-maf-dev.azurewebsites.net \
  STORAGE_BASE_PATH=/home/data/storage \
  SQLITE_DATABASE_PATH=/home/data/app.db
# same blob/SQL as MCP if jobs persist in Azure
```

**UI (`doc-ui-dev`)**

```bash
az webapp config appsettings set -g rg-doc-agent -n doc-ui-dev --settings \
  WEBSITES_PORT=7860 \
  GRADIO_HOST=0.0.0.0 \
  GRADIO_PORT=7860 \
  API_BASE_URL=https://doc-api-dev.azurewebsites.net
```

CORS: if the UI origin is blocked, add the UI hostname to ip_api CORS allowlist.

### 2.6 CORS / MCP HTTP

FastMCP streamable HTTP must be reachable from the **MAF app outbound**. App Service outbound IPs need to reach the MCP Web Apps (public HTTPS is enough).

### 2.7 Verify

```bash
curl -s https://doc-mcp-dev.azurewebsites.net/mcp   # MCP JSON-RPC, not Swagger
curl -s https://doc-maf-dev.azurewebsites.net/health
curl -s https://doc-maf-dev.azurewebsites.net/ask/health
curl -s https://doc-api-dev.azurewebsites.net/health
# Open https://doc-ui-dev.azurewebsites.net
```

GitHub Actions in [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) currently describe **API + UI only**. Extend that workflow for the three extra images if you want CI/CD for MCP + MAF.

---

## 3. Deploy the **chat** agent as a Foundry hosted agent

For a focused operational checklist, use
[FOUNDRY_HOSTED_MAF.md](FOUNDRY_HOSTED_MAF.md).

Scope: this hosts **chat only**. Document generation and voice contracts stay on
the Web App `POST /invoke` job path and are declared `modes: [jobs]` in
`central-agentic-flow/config/mcp_registry.yml`, so no chat host exposes them as
tools. Chat tools come from a separate business MCP, which is configured through
`BUSINESS_MCP_URL` (Web App) or a Toolbox (Foundry) and is optional.

Implemented assets:

| File | Purpose |
|------|---------|
| `../azure.yaml` | Foundry project, model deployment, Responses hosted agent |
| `../central-agentic-flow/foundry_main.py` | Hosted-agent entry point |
| `../central-agentic-flow/toolbox.yaml` | Business MCP Toolbox definition (chat tools only) |
| `../central-agentic-flow/.agentignore` | Direct-code deployment exclusions |

The hosted agent uses:

- `FoundryChatClient` + `DefaultAzureCredential` (managed identity in Azure)
- `ResponsesHostServer` (not FastAPI `/ask`)
- `FoundryToolbox` for the business MCP, attached only when `TOOLBOX_ENDPOINT` is set

### 3.1 Install and authenticate tooling

Install Azure CLI and Azure Developer CLI (`azd`), then install/update the
Foundry extension. Authentication must be completed by you:

```bash
az login
azd auth login
azd extension install azure.ai.agents
```

Every command below should be run from the repository root with:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ...
```

### 3.2 Choose the Foundry project

For a **new** project, `azure.yaml` provisions one with a
`gpt-4.1-mini` Global Standard deployment.

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env new dev
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AZURE_LOCATION "<region>"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "gpt-4.1-mini"
```

For an **existing** project, set its real endpoint / ARM ID and existing model
deployment instead of creating a second model:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AZURE_AI_PROJECT_ENDPOINT \
  "https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AZURE_AI_PROJECT_ID \
  "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<deployment-name>"
```

If using an existing project, review/remove the `ai-project.deployments` block
before `azd provision` so this template does not create an unwanted deployment.

### 3.3 Deploy the business MCP first (optional)

The hosted agent cannot use `127.0.0.1`. If you have a business MCP, deploy it
and verify its endpoint:

```bash
https://<business-mcp-app>.azurewebsites.net/mcp
```

Replace the placeholder URL in `central-agentic-flow/toolbox.yaml`. Public
unauthenticated MCP URLs are acceptable only for a demo; use App Service
authentication/API Management or private networking in production. Do not add
the document or voice MCPs — they belong to the job path.

Without a business MCP, skip to §3.5; the agent deploys and answers tool-less.

### 3.4 Create the Foundry Toolbox

```bash
cd central-agentic-flow
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai toolbox create agent-tools \
  --from-file ./toolbox.yaml
```

Copy the **versioned MCP endpoint** printed by that command:

```bash
cd ..
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set TOOLBOX_ENDPOINT \
  "<versioned-toolbox-mcp-endpoint>"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env get-values
```

Toolbox tools reach the agent with a three-underscore prefix, so business tools
appear as `business___<tool_name>`.

### 3.5 Local smoke test

Create `central-agentic-flow/.env` (never commit it):

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=<deployment-name>
# Optional; omit to run without tools
TOOLBOX_ENDPOINT=<versioned-toolbox-mcp-endpoint>
```

Then:

```bash
cd central-agentic-flow
python -m venv .venv
source .venv/bin/activate
python -m pip install uv
cd ..

AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent run document-maf-foundry --no-client
# second terminal:
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent invoke \
  document-maf-foundry --local "hello, are you up?"
```

Stop the local host after the test.

### 3.6 Provision and deploy

Preview first for a new project:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision --preview --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision --no-prompt
```

For an existing project that needs no infrastructure changes, skip provision.

Deploy and verify:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd deploy document-maf-foundry --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent show --output json
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent invoke \
  document-maf-foundry "list the tools you have access to"
```

Expected status: `active` or `deployed`.

### 3.7 Important compatibility boundary

Foundry Responses covers the conversational path only; it does **not** expose
the FastAPI `POST /invoke`.

- Keep `central-agentic-flow` as a Web App: `ip_api` submits document and voice
  jobs through `MAF_BASE_URL/invoke`, and those MCPs are jobs-only.
- Do not point `MAF_BASE_URL` at the Foundry Responses endpoint.
- The document and voice MCP Web Apps are reached by the MAF Web App directly,
  not through the Toolbox.
- A future API adapter can split `MAF_CHAT_ENDPOINT` (Foundry) from
  `MAF_INVOKE_BASE_URL` (Web App); that change is intentionally not required
  to deploy/test this hosted chat agent.
