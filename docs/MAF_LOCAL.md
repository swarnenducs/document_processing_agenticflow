# MAF = central-agentic-flow (self-contained, own prompts/)

```text
central-agentic-flow/
  src/central_agentic_flow/
  config/mcp_registry.yml
  config/prompt_versions.json      # required prompt versions
  prompts/                         # {name}.{version}.md files
  Dockerfile
```

```bash
uv sync
python run_all_components.py
```

MCP registry: edit `central-agentic-flow/config/mcp_registry.yml`  
(or `MAF_MCP_REGISTRY_FILE` / one-off `MAF_EXTRA_MCPS`).

Preamble: versioned files under `central-agentic-flow/prompts/`; required version in
`central-agentic-flow/config/prompt_versions.json`
(`MAF_PROMPT_VERSIONS_FILE` / `MAF_PROMPTS_DIR`).

Persona is sent on `/ask` (not loaded from files). Confidence floor:
`MAF_PERSONA_VALIDATOR_MIN_CONFIDENCE` (default `0.95`).
See [MAF_PROMPT_GUARDRAILS.md](MAF_PROMPT_GUARDRAILS.md).

See [COMPONENTS.md](COMPONENTS.md).

**Azure:** Foundry as the **LLM** + Web Apps for MAF/MCP — [AZURE_DEPLOY_MAF.md](AZURE_DEPLOY_MAF.md).
