# MAF = central-agentic-flow (self-contained, own prompts/)

```text
central-agentic-flow/
  src/central_agentic_flow/
  config/mcp_registry.yml          # MCP URLs, prompts, invoke rules
  prompts/orchestrator_instructions.md
  Dockerfile
```

```bash
uv sync
python run_all_components.py
```

MCP registry: edit `central-agentic-flow/config/mcp_registry.yml`  
(or `MAF_MCP_REGISTRY_FILE` / one-off `MAF_EXTRA_MCPS`).

Preamble: edit `central-agentic-flow/prompts/orchestrator_instructions.md`  
or set `MAF_INSTRUCTIONS` / `MAF_INSTRUCTIONS_FILE` / `MAF_PROMPTS_DIR`.

See [COMPONENTS.md](COMPONENTS.md).

**Azure:** Foundry as the **LLM** + Web Apps for MAF/MCP — [AZURE_DEPLOY_MAF.md](AZURE_DEPLOY_MAF.md).
