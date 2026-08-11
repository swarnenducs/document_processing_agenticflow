# Split-ready components — each folder is self-contained (can become its own git).
# Shared helpers are **duplicated inside** each package (no shared_core package/repo).

```text
document-processing-mcp/     # document LangGraph + MCP :8001 + prompts/
voice_enable_mcp/            # voice LangGraph + MCP :8002 + prompts/
central-agentic-flow/        # MAF :8003 + prompts/
ip_api/                      # FastAPI :8000
UI/                          # Gradio :7860

run_all_components.py        # root launcher
docker-compose.yml
```

## Prompts (per component)

| Component | Folder | Env override |
|---|---|---|
| Document | `document-processing-mcp/prompts/` | `DOCUMENT_PROMPTS_DIR` |
| Voice | `voice_enable_mcp/prompts/` | `VOICE_PROMPTS_DIR` |
| MAF | `central-agentic-flow/prompts/` | `MAF_PROMPTS_DIR` / `MAF_INSTRUCTIONS_FILE` |

## Local (all including MAF)

```bash
uv sync
python run_all_components.py
```

## Docker

```bash
docker compose up --build
```

## Split into separate gits

Each of `document-processing-mcp`, `voice_enable_mcp`, `central-agentic-flow`, `ip_api`, `UI` can be copied to its own repo as-is (includes duplicated core/storage/llm helpers). Wire them with env URLs only.
