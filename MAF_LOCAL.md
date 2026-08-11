# MAF = central-agentic-flow (self-contained, own prompts/)

```text
central-agentic-flow/
  src/central_agentic_flow/
  prompts/orchestrator_instructions.md
  Dockerfile
```

```bash
uv sync
python run_all_components.py
```

Prompts: edit `central-agentic-flow/prompts/orchestrator_instructions.md`  
or set `MAF_INSTRUCTIONS` / `MAF_INSTRUCTIONS_FILE` / `MAF_PROMPTS_DIR`.

See [COMPONENTS.md](COMPONENTS.md).
