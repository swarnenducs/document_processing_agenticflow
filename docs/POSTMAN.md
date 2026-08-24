# Postman

Import these JSON files in Postman (or Insomnia/Bruno that accept Collection v2.1). Do **not** put API keys or SQL passwords in the collection.

| File | What |
|------|------|
| [postman/IPP.postman_collection.json](../postman/IPP.postman_collection.json) | Gateway + MAF requests |
| [postman/local.postman_environment.json](../postman/local.postman_environment.json) | `baseUrl` `:8000`, `mafUrl` `:8003` |
| [postman/azure.postman_environment.json](../postman/azure.postman_environment.json) | Replace `<api-app>` / `<maf-app>` |

The same three files are copied to [ip_api/postman/](../ip_api/postman/) so a split `ip_api` git still has them.

## Import

1. Start the stack (`python run_all_components.py`) or only `ip_api` + MAF + MCPs.
2. Postman → **Import** → select the collection and **IPP local**.
3. Send **Gateway → Health**. Then **Voice → Start contract** (saves `thread_id`) → **Confirm**.
4. For document jobs: **Documents → Create job** and attach a `.docx` from `samples/templates/`.

Swagger alternative: `http://127.0.0.1:8000/docs` (`/openapi.json`).

Document and voice **MCP** (`:8001/mcp`, `:8002/mcp`) are not OpenAPI. Use the collection’s gateway or **MAF direct → Invoke**.

UI (Gradio `:7860`) is not in Postman.

Set `adminKey` in the environment if you call **Admin templates** (`X-Admin-Api-Key`).
