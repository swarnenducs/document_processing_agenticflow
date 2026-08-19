# Tests live in each component (split-ready).

```bash
uv run pytest                          # all components
cd document-processing-mcp && pytest   # one package
```

| Package | Folder |
|---|---|
| document-processing-mcp | `document-processing-mcp/tests/` |
| voice_enable_mcp | `voice_enable_mcp/tests/` |
| central-agentic-flow | `central-agentic-flow/tests/` |
| ip_api | `ip_api/tests/` |
| UI | `UI/tests/` |
