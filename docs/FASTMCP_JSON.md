# FastMCP responses: JSON object vs JSON text

**Short answer:** tools return **Pydantic models**. FastMCP serializes them as a **JSON object** (`structuredContent` / `result.data`). It may also copy that object into a **text** block for the LLM. Clients read the object.

## What tools return

Return type is a `BaseModel`, not `dict[str, Any]` and not `json.dumps(...)`.

| Server | Tool | Model |
|--------|------|--------|
| document `:8001` | `health` | `McpHealthResponse` |
| document `:8001` | `generate_document` | `GenerateDocumentResponse` |
| voice `:8002` | `health` | `McpHealthResponse` |
| voice `:8002` | `start_voice_contract` / `confirm_voice_contract` | `VoiceContractMcpResponse` |
| voice `:8002` | `list_voice_contracts` | `VoiceContractListResponse` |

```python
@self.tool
def health() -> McpHealthResponse:
    return McpHealthResponse(ok=True, mcp="document_process_mcp", agent="document_process_mcp")
```

Pydantic gives FastMCP an **output JSON schema**, so `structuredContent` is a typed object (`{"ok": true, ...}`).

## What is on the wire (MCP `CallToolResult`)

| Field | Shape | Meaning |
|--------|--------|---------|
| `structuredContent` | JSON **object** | Canonical payload from the Pydantic model |
| `content[0].text` | JSON **as text** | Same payload stringified for the model |
| FastMCP `result.data` | dict (or model) | Deserialized structured JSON |

Prefer the object. Do not `return json.dumps(...)` from a tool.

## How this repo reads it

Unwrap (`tool_result_payload`): `result.data` → `structured_content` → text. If the value is still a Pydantic instance, `model_dump(mode="json")`.

`POST /api/v1/agents/*` then returns that dict as FastAPI `application/json`.
