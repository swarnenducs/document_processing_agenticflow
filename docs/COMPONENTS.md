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

Each of `document-processing-mcp`, `voice_enable_mcp`, `central-agentic-flow`, `ip_api`, `UI` can be copied to its own repo. Each folder has `.env.example`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `Dockerfile`, `run.py`, `run.sh`, and `tests/` (`pytest`).

```bash
cd document-processing-mcp   # or voice_enable_mcp / central-agentic-flow / ip_api / UI
python -m pip install -r requirements.txt
cp .env.example .env
./run.sh
```

Wire them with URLs only: `CENTRAL_AGENT_END_POINT` (alias `MAF_BASE_URL`), `TEMPLATE_PROCESSING_END_POINT` / `VOICE_PROCESSING_END_POINT` (aliases `DOCUMENT_MCP_URL` / `VOICE_MCP_URL`), `API_BASE_URL`.

Postman (gateway + MAF, not Gradio/MCP JSON-RPC): [POSTMAN.md](POSTMAN.md). Split `ip_api` repos can use [ip_api/postman/](../ip_api/postman/).
