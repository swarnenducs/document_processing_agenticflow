# Voice MCP prompts (LangChain ChatPromptTemplate YAML)

Each file needs `system` + `human` strings. Variables use `{name}`; literal braces are `{{` `}}`.

```yaml
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
