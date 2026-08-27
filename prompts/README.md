# Prompts live inside each component

Each component has `config/prompt_versions.json`. That JSON names the
**required_version**; the loader uses `prompts/{name}.{version}.*`.

| Component | Prompts | Version JSON |
|---|---|---|
| Document | `document-processing-mcp/prompts/*.{version}.yml` | `document-processing-mcp/config/prompt_versions.json` |
| Voice | `voice_enable_mcp/prompts/*.{version}.yml` | `voice_enable_mcp/config/prompt_versions.json` |
| MAF | `central-agentic-flow/prompts/*.{version}.md` | `central-agentic-flow/config/prompt_versions.json` |

Env (optional path override): `DOCUMENT_PROMPT_VERSIONS_FILE`,
`VOICE_PROMPT_VERSIONS_FILE`, `MAF_PROMPT_VERSIONS_FILE`.
Folder override: `DOCUMENT_PROMPTS_DIR`, `VOICE_PROMPTS_DIR`, `MAF_PROMPTS_DIR`.

Architecture: [docs/README.md](../docs/README.md),
[docs/MAF_PROMPT_GUARDRAILS.md](../docs/MAF_PROMPT_GUARDRAILS.md).
