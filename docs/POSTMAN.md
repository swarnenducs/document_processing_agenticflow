# Postman

Import these JSON files in Postman (or Insomnia/Bruno that accept Collection v2.1). Do **not** put API keys or SQL passwords in the collection.

| File | What |
|------|------|
| [postman/IPP.postman_collection.json](../postman/IPP.postman_collection.json) | **ipp_agentic_api** + MAF requests |
| [postman/local.postman_environment.json](../postman/local.postman_environment.json) | `baseUrl` `:8000`, `mafUrl` `:8003` |
| [postman/azure.postman_environment.json](../postman/azure.postman_environment.json) | Replace `<api-app>` / `<maf-app>` |

The collection folders: **Gateway** (health, OpenAPI JSON, chat), **Documents**, **Audio (STT only)**, **Voice**, **Agents via MAF**, **MAF direct**, **Admin templates**. Each request has a description in Postman.

## Import

1. Start the stack (`python run_all_components.py`) or only `ip_api` + MAF + MCPs.
2. Postman → **Import** → select the collection and **IPP local**.
3. Send **Gateway → Health**. Then **Voice → Start contract** (saves `thread_id`) → **Confirm**.
4. For document jobs: **Documents → Create job** and attach a `.docx` from `samples/templates/`.

Swagger (human-readable): `http://127.0.0.1:8000/docs` — each operation has a summary, tag, and how-to text. Schema: `/openapi.json`. ReDoc: `/redoc`.

Document and voice **MCP** (`:8001/mcp`, `:8002/mcp`) are not OpenAPI. Use the collection’s gateway or **MAF direct → Invoke**.

UI (Gradio `:7860`) is not in Postman.

Set `adminKey` in the environment if you call **Admin templates** (`X-Admin-Api-Key`).
