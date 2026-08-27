# Voice MCP prompts (LangChain ChatPromptTemplate YAML)

Each file needs `version`, `system`, and `human`. Variables use `{name}`; literal braces are `{{` `}}`.

Required versions: `voice_enable_mcp/config/prompt_versions.json`
(`VOICE_PROMPT_VERSIONS_FILE` to override). Files are `intent.{version}.yml` /
`confirm.{version}.yml`.

```yaml
version: "1.0.0"
name: example
system: |
  You are the voice/contract helper.
human: |
  Transcript: {transcript}
```

Runtime LCEL (`ChatPromptTemplate | structured LLM`):

| File | Chain | Used in |
|---|---|---|
| `intent.yml` | `build_intent_chain(llm)` | `parse_intent_node` |
| `confirm.yml` | `build_confirm_chain(llm)` | `await_confirmation_node` |

Uses mapper LLM credentials when available; otherwise regex fallback.

Load with `chat_prompt_from_yaml("intent.yml")` then `| llm` (LCEL) or `.format_messages(...)`.

Override directory: `VOICE_PROMPTS_DIR` or `PROMPTS_DIR`.
