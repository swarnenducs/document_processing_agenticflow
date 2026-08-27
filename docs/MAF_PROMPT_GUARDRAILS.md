# Persona Prompt Validator (LLM gate before execute)

Chat `/ask` does **not** use a question catalog or per-persona files.
`Persona` on the request **is** the definition. Chat tools are **shared**.

Prompt **files** are versioned. The required version is in
[`central-agentic-flow/config/prompt_versions.json`](../central-agentic-flow/config/prompt_versions.json).
Change `required_version` there to select `*.{version}.md` (file frontmatter
must match). Document and voice MCP use the same pattern in their
`config/prompt_versions.json`.

## Request

```json
{
  "Prompt": "how many contracts going to expire in the next quarter",
  "Persona": "<persona definition from the client>"
}
```

Aliases: `message` → Prompt, `role` → Persona. Missing Prompt or Persona → **400**.

## What happens

1. Read the required validator version from `prompt_versions.json`.
2. Load that file (`prompts/guardrails/persona_prompt_validator.{version}.md`).
3. Run the validator LLM with Persona Definition, User Prompt, and available tools.
4. Execute only when classification allows it **and** `confidence` meets
   `MAF_PERSONA_VALIDATOR_MIN_CONFIDENCE` (default **0.95**).

`GET /prompts` returns each prompt’s `required_version` and resolved path.

To ship a new validator: add `persona_prompt_validator.1.1.0.md` and set
`"required_version": "1.1.0"` in the JSON. Same for MCP YAML prompts.
