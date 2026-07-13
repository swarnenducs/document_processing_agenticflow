# Deployment Guide — Azure Web Apps + GitHub Actions

How to **build, test, and deploy** Document Processing Agentic Flow to **Azure App Service (Web Apps)** using **GitHub Actions**.

Related docs:

- Local setup & features → [README.md](README.md)
- Interview / architecture prep → [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- Env template → [.env.example](.env.example)

---

## Table of contents

1. [Architecture on Azure](#1-architecture-on-azure)
2. [Prerequisites](#2-prerequisites)
3. [Step-by-step: create Azure resources](#3-step-by-step-create-azure-resources)
4. [Configure App Settings](#4-configure-app-settings)
5. [Configure GitHub (secrets & variables)](#5-configure-github-secrets--variables)
6. [What the pipelines do](#6-what-the-pipelines-do)
7. [Deploy](#7-deploy)
8. [Verify](#8-verify)
9. [Alternative: zip / code deploy (no Docker)](#9-alternative-zip--code-deploy-no-docker)
10. [Local Docker smoke test](#10-local-docker-smoke-test)
11. [Troubleshooting](#11-troubleshooting)
12. [Production hardening](#12-production-hardening)
13. [Checklist](#13-checklist)

---

## 1. Architecture on Azure

This app has **two processes**:

| App | Command | Port | URL example |
|-----|---------|------|-------------|
| FastAPI backend | `uv run doc-api` | `8000` | `https://doc-api-dev.azurewebsites.net` |
| Gradio UI | `uv run doc-ui` | `7860` | `https://doc-ui-dev.azurewebsites.net` |

Azure Web App exposes **one public port per app**. Use **two Web Apps** (recommended), or deploy **API only**.

```text
                    GitHub Actions (on push to main)
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   Azure Web App: API                  Azure Web App: UI
   (container, port 8000)              (container, port 7860)
              │                                 │
              │◄──── API_BASE_URL = https://doc-api-….azurewebsites.net
              │
         SQLite + files under /home/data
         (mount Azure Files for persistence)
```

**Recommended deploy style:** Docker image → **Azure Container Registry (ACR)** → **Web App for Containers**.

Repo assets:

| File | Role |
|------|------|
| `Dockerfile` | Builds API or UI image (`APP_TARGET=api` or `ui`) |
| `.github/workflows/ci.yml` | Tests on PR / push |
| `.github/workflows/deploy-azure.yml` | Tests → build → push ACR → deploy Web Apps |

---

## 2. Prerequisites

- Azure subscription + [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
- GitHub repo with this project
- Docker (for local image smoke tests)
- API keys for LLMs (OpenAI mapper, Groq validator) — same as local `.env`

---

## 3. Step-by-step: create Azure resources

```bash
az login

# Resource group
az group create -n rg-doc-agent -l eastus

# Linux App Service plan (B1 is fine for demos)
az appservice plan create \
  -g rg-doc-agent -n plan-doc-agent \
  --is-linux --sku B1

# Container registry (name must be globally unique)
az acr create -g rg-doc-agent -n docagentacr$((RANDOM % 100000)) --sku Basic
# Save ACR name, e.g. docagentacr48291 → login server: docagentacr48291.azurecr.io

# Web Apps (placeholder image; GitHub Actions replaces it)
az webapp create \
  -g rg-doc-agent -p plan-doc-agent -n doc-api-dev \
  --deployment-container-image-name nginx

az webapp create \
  -g rg-doc-agent -p plan-doc-agent -n doc-ui-dev \
  --deployment-container-image-name nginx
```

> Web app names must be globally unique. Change `doc-api-dev` / `doc-ui-dev` if taken.

Optional but recommended: attach an **Azure File share** at `/home/data` so jobs and SQLite survive restarts (App Service → Configuration → Path mappings).

---

## 4. Configure App Settings

### 4.1 API Web App (`doc-api-dev`)

```bash
az webapp config appsettings set -g rg-doc-agent -n doc-api-dev --settings \
  WEBSITES_PORT=8000 \
  API_HOST=0.0.0.0 \
  API_PORT=8000 \
  STORAGE_BASE_PATH=/home/data/storage \
  SQLITE_DATABASE_PATH=/home/data/app.db \
  OPENAI_API_KEY="<your-openai-key>" \
  GROQ_API_KEY="<your-groq-key>" \
  MAPPER_PROVIDER=openai \
  OPENAI_MODEL=gpt-5 \
  VALIDATOR_PROVIDER=groq \
  GROQ_VALIDATOR_MODEL=openai/gpt-oss-120b \
  SPEECH_PROVIDER=openai
```

### 4.2 UI Web App (`doc-ui-dev`)

```bash
az webapp config appsettings set -g rg-doc-agent -n doc-ui-dev --settings \
  WEBSITES_PORT=7860 \
  GRADIO_HOST=0.0.0.0 \
  GRADIO_PORT=7860 \
  API_BASE_URL=https://doc-api-dev.azurewebsites.net
```

The UI only needs `API_BASE_URL` (and port/host). LLM keys stay on the API app.

### 4.3 Settings matrix

| Setting | API | UI |
|---------|-----|-----|
| `WEBSITES_PORT` | `8000` | `7860` |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | — |
| `GRADIO_HOST` / `GRADIO_PORT` | — | `0.0.0.0` / `7860` |
| `API_BASE_URL` | optional | `https://<api-app>.azurewebsites.net` |
| `STORAGE_BASE_PATH` | `/home/data/storage` | — |
| `SQLITE_DATABASE_PATH` | `/home/data/app.db` | — |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | yes | no |

Never commit real keys. Prefer Azure Key Vault references in production.

---

## 5. Configure GitHub (secrets & variables)

### 5.1 Create a service principal

```bash
az ad sp create-for-rbac \
  --name "sp-doc-agent-gha" \
  --role contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-doc-agent \
  --sdk-auth
```

Copy the JSON output into a GitHub secret named **`AZURE_CREDENTIALS`**.

### 5.2 ACR credentials

```bash
az acr credential show -n <ACR_NAME>
```

### 5.3 GitHub Secrets

**Settings → Secrets and variables → Actions → Secrets**

| Secret | Value |
|--------|--------|
| `AZURE_CREDENTIALS` | Service principal JSON |
| `ACR_LOGIN_SERVER` | e.g. `docagentacr48291.azurecr.io` |
| `ACR_USERNAME` | From `az acr credential show` |
| `ACR_PASSWORD` | From `az acr credential show` |

### 5.4 GitHub Variables

**Settings → Secrets and variables → Actions → Variables**

| Variable | Example |
|----------|---------|
| `AZURE_RESOURCE_GROUP` | `rg-doc-agent` |
| `AZURE_API_WEBAPP_NAME` | `doc-api-dev` |
| `AZURE_UI_WEBAPP_NAME` | `doc-ui-dev` (omit to skip UI deploy) |
| `IMAGE_NAME` | `doc-agent` (optional) |

---

## 6. What the pipelines do

### CI — `.github/workflows/ci.yml`

**When:** pull requests and pushes to `main` / `master`

```text
checkout → uv sync → ruff → pytest
```

Tests run **without** live LLM keys (rule fallbacks).

### CD — `.github/workflows/deploy-azure.yml`

**When:** push to `main` / `master`, or manual **workflow_dispatch**

```text
pytest gate
  → docker build APP_TARGET=api  → push ACR → deploy API Web App
  → docker build APP_TARGET=ui   → push ACR → deploy UI Web App (if configured)
  → curl /api/v1/health smoke check
```

---

## 7. Deploy

1. Commit and push to `main` (or run **Actions → Deploy Azure → Run workflow**).
2. Open the workflow run and wait for green.
3. Azure Portal → each Web App → **Deployment Center** / **Container settings** should show the new ACR image tag.

**API-only (fastest demo):** create only the API Web App, leave `AZURE_UI_WEBAPP_NAME` unset, and point local Gradio at Azure:

```bash
export API_BASE_URL=https://doc-api-dev.azurewebsites.net
uv run doc-ui
```

---

## 8. Verify

```bash
# Health
curl https://doc-api-dev.azurewebsites.net/api/v1/health

# Create a document job
curl -X POST https://doc-api-dev.azurewebsites.net/api/v1/documents/jobs \
  -F "template=@samples/templates/invoice_template.docx" \
  -F "data=@samples/data/invoice.json;type=application/json"

# Poll status (use job_id from response)
curl https://doc-api-dev.azurewebsites.net/api/v1/documents/jobs/<job_id>

# UI in browser
open https://doc-ui-dev.azurewebsites.net
```

Swagger: `https://doc-api-dev.azurewebsites.net/docs`

If the site fails to start, open **Log stream** in the Azure Portal.

---

## 9. Alternative: zip / code deploy (no Docker)

Use this if you prefer classic App Service Python deploy. The repo already includes pinned `requirements.txt` (from `uv.lock`).

```bash
# regenerate if dependencies change
uv export --no-dev --no-hashes --output-file requirements.txt
```

**API startup command** (App Service → Configuration → General settings):

```bash
python -m pip install -r requirements.txt && python -m uvicorn document_processing_agenticflow.api.main:app --host 0.0.0.0 --port 8000
```

**UI startup command:**

```bash
python -m pip install -r requirements.txt && python -m document_processing_agenticflow.ui.gradio_app
```

(`requirements.txt` already includes `-e .` so the local package is installed editable from the repo root.)

---

## 10. Local Docker smoke test

```bash
# API
docker build --build-arg APP_TARGET=api -t doc-agent-api .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY -e GROQ_API_KEY \
  -e STORAGE_BASE_PATH=/tmp/storage \
  -e SQLITE_DATABASE_PATH=/tmp/app.db \
  doc-agent-api

curl http://127.0.0.1:8000/api/v1/health

# UI → local API
docker build --build-arg APP_TARGET=ui -t doc-agent-ui .
docker run --rm -p 7860:7860 \
  -e API_BASE_URL=http://host.docker.internal:8000 \
  -e GRADIO_HOST=0.0.0.0 \
  -e GRADIO_PORT=7860 \
  doc-agent-ui
```

---

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Application Error / container exits | Set `WEBSITES_PORT` to match app; bind `0.0.0.0` |
| UI open but Generate fails | Fix `API_BASE_URL` on UI app; confirm API health |
| Jobs vanish after restart | Mount Azure Files at `/home/data` |
| ACR pull unauthorized | Fix ACR credentials / enable admin / assign AcrPull to Web App identity |
| LLM / Whisper failures | Missing `OPENAI_API_KEY` / `GROQ_API_KEY` on **API** app |
| Upload 413 | Raise `MAX_UPLOAD_MB` and App Service limits |

---

## 12. Production hardening

| Area | Next step |
|------|-----------|
| Secrets | Azure Key Vault + Key Vault references |
| Auth | Easy Auth / Entra ID / API keys on FastAPI |
| Async jobs | Azure Queue / Service Bus instead of in-process `BackgroundTasks` |
| Files | Azure Blob Storage for `.docx` / audio |
| Metadata | Managed DB instead of local SQLite |
| Monitoring | Application Insights |
| Envs | GitHub Environments (`dev` / `staging` / `prod`) with approval |

These are good **interview follow-ups** when asked “how would you productionize this?”

---

## 13. Checklist

- [ ] Resource group + Linux plan created  
- [ ] ACR created; login server noted  
- [ ] `doc-api` Web App created (`WEBSITES_PORT=8000`)  
- [ ] (Optional) `doc-ui` Web App created (`WEBSITES_PORT=7860`, `API_BASE_URL` set)  
- [ ] API keys and storage paths set on API app  
- [ ] GitHub secrets: `AZURE_CREDENTIALS`, `ACR_*`  
- [ ] GitHub variables: resource group + web app names  
- [ ] Push to `main` → **Deploy Azure** succeeds  
- [ ] `/api/v1/health` returns 200  
- [ ] One document job completes; download works  
- [ ] (Optional) Azure Files mounted at `/home/data`  

---

## Quick reference — URLs after deploy

```text
API health:  https://<api-app>.azurewebsites.net/api/v1/health
API docs:    https://<api-app>.azurewebsites.net/docs
UI:          https://<ui-app>.azurewebsites.net
```
