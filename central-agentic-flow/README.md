# central-agentic-flow

MAF orchestrator (`:8003`). Copy this folder to its own git.

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest
cp .env.example .env
./run.sh
# or: python run.py
```

Set `DOCUMENT_MCP_URL` and `VOICE_MCP_URL` (env overrides `config/mcp_registry.yml`).
