# Prompts live inside each component (do not keep YAML here)

| Component | Path |
|---|---|
| Document | `document-processing-mcp/prompts/` — `mapper.yml`, `validator.yml`, `extraction_validator.yml`, `agent.yml` (all LangChain `ChatPromptTemplate`) |
| Voice | `voice_enable_mcp/prompts/` — `intent.yml`, `confirm.yml` (LCEL `ChatPromptTemplate \| llm`) |
| MAF | `central-agentic-flow/prompts/orchestrator_instructions.md` + registry YAML; each ask formatted via `ChatPromptTemplate` |

Env: `DOCUMENT_PROMPTS_DIR`, `VOICE_PROMPTS_DIR`, `MAF_PROMPTS_DIR`

Architecture and interview notes: [docs/README.md](../docs/README.md)
