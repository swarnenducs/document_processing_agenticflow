# central-agentic-flow

MAF orchestrator (`:8003`). Copy this folder to its own git.

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest
cp .env.example .env
./run.sh
# or: python run.py
```

Set `TEMPLATE_PROCESSING_END_POINT` (alias `DOCUMENT_MCP_URL`) and `VOICE_PROCESSING_END_POINT` (alias `VOICE_MCP_URL`); env overrides `config/mcp_registry.yml`.

## Chat and jobs are segregated

`config/mcp_registry.yml` decides which MCP each path can reach:

| Path | Endpoint | MCPs | Mode |
|---|---|---|---|
| Chat | `POST /ask`, Foundry `/responses` | business (`BUSINESS_MCP_URL`), optional chat (`CHAT_MCP_END_POINT`) | `[ask]` |
| Jobs | `POST /invoke` | document, voice, optional metadata (`METADATA_EXTRACTION_END_POINT`) | `[jobs]` |

The LLM is never given the document, voice, or metadata tools. Ask-mode URLs
are optional: when unset, chat answers without tools and redirects job
requests to the API. How to attach chat/metadata:
[docs/ADD_MAF_MCP_AGENTS.md](../docs/ADD_MAF_MCP_AGENTS.md).

## Microsoft Foundry hosted chat agent

`foundry_main.py` serves the chat path through the Foundry Responses protocol,
using managed identity and an optional Foundry Toolbox instead of localhost MCP
URLs.

Required settings:

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=<deployment-name>
# Optional business Toolbox; omit to run without tools
TOOLBOX_ENDPOINT=<versioned-toolbox-mcp-endpoint>
```

Deployment is configured by the repository-root `azure.yaml`. Replace the MCP
URL placeholders in `toolbox.yaml`, then follow
[`docs/AZURE_DEPLOY_MAF.md`](../docs/AZURE_DEPLOY_MAF.md#3-deploy-maf-as-a-foundry-hosted-agent).

The existing FastAPI server remains required for `ip_api` calls to
`POST /invoke`; the hosted agent is the conversational endpoint.
