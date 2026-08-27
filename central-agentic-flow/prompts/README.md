# MAF / central-agentic-flow prompts

LLM prompts are external files. **Required versions** live in
`config/prompt_versions.json`. The loader uses `{name}.{version}.md`.

- `guardrails/persona_prompt_validator.{version}.md` — LLM validator; before execute
- `guardrails/role_access.{version}.md` — reminder for the answering agent
- `orchestrator_instructions.{version}.md` — shared chat preamble

Persona definition is **not** a file. Send it on `/ask` as `Persona`.

Override the JSON path with `MAF_PROMPT_VERSIONS_FILE`.
Override the prompts folder with `MAF_PROMPTS_DIR`.
