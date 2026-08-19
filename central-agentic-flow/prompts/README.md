# MAF / central-agentic-flow prompts

- `orchestrator_instructions.md` — shared system-prompt **preamble**
- Per-MCP invoke rules and tool prompts: `../config/mcp_registry.yml`

Each `/ask` turn is formatted with LangChain `ChatPromptTemplate`
(`system` + `human`) before MAF `Agent` runs.

Env: `MAF_INSTRUCTIONS` or `MAF_INSTRUCTIONS_FILE` (preamble only).
`MAF_MCP_REGISTRY_FILE` overrides the YAML registry path.
