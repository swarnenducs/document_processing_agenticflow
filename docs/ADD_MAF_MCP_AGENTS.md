# Add Chat and Metadata MCP agents to MAF

Step-by-step for attaching two **optional** MCP servers to the central MAF
agent. This repo already has the **config hooks**. You still need to build the
FastMCP packages yourself — filling a URL is what attaches them.

Related: [MCP_AGENTS.md](MCP_AGENTS.md) ·
[interview-prep/flow-understanding/adding-a-new-flow.md](interview-prep/flow-understanding/adding-a-new-flow.md) ·
[FOUNDRY_HOSTED_MAF.md](FOUNDRY_HOSTED_MAF.md) ·
[ENVIRONMENT.md](ENVIRONMENT.md) ·
[AZURE_WEBAPP_SETTINGS.md](AZURE_WEBAPP_SETTINGS.md)

## Jobs vs chat (do not mix)

```text
UI / ip_api
    │
    ├── POST /api/ask  ──────────► MAF POST /ask  ──► ask-mode MCPs only
    │                              Foundry /responses     (business, chat)
    │                              Foundry Toolbox        (chat-only)
    │
    └── document/voice/metadata
        jobs ────────────────────► MAF POST /invoke ──► jobs-mode MCPs
                                   (document, voice, metadata)
```

| MCP | Registry `name` (alias) | Mode | Preferred env | Alias | Suggested local port |
|---|---|---|---|---|---|
| Document (existing) | `contract-autocreation-mcp` (`document`) | `[jobs]` | `TEMPLATE_PROCESSING_END_POINT` | `DOCUMENT_MCP_URL` | `:8001` |
| Voice (existing) | `voice-agent` (`voice`) | `[jobs]` | `VOICE_PROCESSING_END_POINT` | `VOICE_MCP_URL` | `:8002` |
| Business (optional, existing) | `business-agent` (`business`) | `[ask]` | `BUSINESS_MCP_URL` | — | `:8006` |
| **Chat (optional, new)** | `chat-agent` (`chat`) | `[ask]` | `CHAT_MCP_END_POINT` | `CHAT_MCP_URL` | `:8004` |
| **Metadata (optional, new)** | `metadata-agent` (`metadata`) | `[jobs]` | `METADATA_EXTRACTION_END_POINT` | `METADATA_MCP_URL` | `:8005` |

MAF itself stays on `:8003`. Chat and business are **siblings**: set both URLs
and both attach. Chat does **not** replace business.

Empty URL → the YAML entry is skipped. Current deploys need no change.

---

## A) Chat MCP (`modes: [ask]`)

Chat tools are for `POST /ask` and the Foundry hosted agent. They are **not**
callable via `POST /invoke`.

### 1. New FastMCP package

Copy `document-processing-mcp/` (or `voice_enable_mcp/`) into a new folder, e.g.
`chat_enable_mcp/`. Own `src/`, `prompts/`, `Dockerfile`, and HTTP `/mcp`.

Suggested local bind: **`:8004`**.

Implement `@self.tool` functions the LLM should call. Do **not** put document
generation, metadata extraction, or voice contracts in this server.

### 2. Registry YAML (already present)

`central-agentic-flow/config/mcp_registry.yml` already has:

```yaml
  - name: chat-agent
    aliases: [chat]
    mcp: chat_process_mcp
    enabled: true
    url: "${CHAT_MCP_END_POINT:-}"
    prefix: chat
    invoke:
      modes: [ask]
```

Leave `enabled: true`. The empty `${CHAT_MCP_END_POINT:-}` default keeps the
server off until the env URL is set. After you add tools, extend `invoke.tools`
and `instructions` with `when:` text so `/ask` knows when to call them.

### 3. Env URL (this is the attach switch)

Local (commented in `.env.example` until you run the server):

```bash
CHAT_MCP_END_POINT=http://127.0.0.1:8004/mcp
# CHAT_MCP_URL=http://127.0.0.1:8004/mcp   # alias; preferred name wins
```

Azure Application settings (empty in
`central-agentic-flow/config/azure-webapp.settings.json` today):

```text
CHAT_MCP_END_POINT=https://<chat-mcp-app>.azurewebsites.net/mcp
```

Use a real HTTPS `/mcp` hostname. **Never localhost** in Azure JSON.

Resolution: `CHAT_MCP_END_POINT` → `CHAT_MCP_URL` → absent.

Optional sibling:

```bash
BUSINESS_MCP_URL=http://127.0.0.1:8006/mcp
```

### 4. Invoke vs ask

| Path | Chat MCP? |
|---|---|
| MAF `POST /ask` | Yes — LLM may call `chat_*` tools |
| Foundry `/responses` + Toolbox | Yes — add this MCP to `toolbox.yaml` (chat-only) |
| MAF `POST /invoke` | **No** — `assert_jobs_invoke` rejects `modes: [ask]` |

### 5. Foundry Toolbox (chat-only)

If you host chat on Foundry, add a **second** MCP entry in
`central-agentic-flow/toolbox.yaml` (keep `business` if you have it):

```yaml
  - type: mcp
    server_label: chat
    server_url: "https://<chat-mcp-app>.azurewebsites.net/mcp"
    require_approval: "never"
```

Do **not** put metadata, document, or voice in the Toolbox.

### 6. Azure JSON fill-in

In `central-agentic-flow/config/azure-webapp.settings.json` set
`CHAT_MCP_END_POINT` (and optionally `CHAT_MCP_URL` to the same value). Leave
empty until the chat Web App exists.

### 7. Tests / smoke

```bash
cd central-agentic-flow
# URL unset → chat-agent absent; URL set → present and ask-only
python -m pytest tests/test_maf_orchestrator.py -k "chat_mcp or optional_chat"
```

With the server running:

```bash
curl -s http://127.0.0.1:8000/api/v1/agents/tools | jq
curl -s http://127.0.0.1:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"message":"Use the chat tools to answer …"}'
```

---

## B) Metadata extraction MCP (`modes: [jobs]`)

Metadata is a **job**, like document generate. Callers name the tool on
`POST /invoke`. The LLM on `/ask` never sees it.

### 1. New FastMCP package

New folder, e.g. `metadata_extraction_mcp/`. Suggested local bind: **`:8005`**.

Implement at least:

- `health` — liveness
- `extract_metadata` — the job tool (`source_path` plus whatever you need)

The registry already names `extract_metadata` so `/invoke` can target it once
the MCP exists.

### 2. Registry YAML (already present)

```yaml
  - name: metadata-agent
    aliases: [metadata]
    mcp: metadata_process_mcp
    enabled: true
    url: "${METADATA_EXTRACTION_END_POINT:-}"
    prefix: metadata
    invoke:
      modes: [jobs]
      default_tool: extract_metadata
      tools:
        extract_metadata:
          when: >
            Extract structured metadata from a document. Use for
            metadata-extraction jobs once this MCP is deployed.
          request:
            required: [source_path]
            optional: [job_id, xid, schema]
```

After you build the MCP, keep `invoke.tools` in sync with real tool names and
request fields. Prefix on the wire is `metadata_` (`metadata_extract_metadata`).

### 3. Env URL

```bash
METADATA_EXTRACTION_END_POINT=http://127.0.0.1:8005/mcp
# METADATA_MCP_URL=http://127.0.0.1:8005/mcp   # alias
```

Azure:

```text
METADATA_EXTRACTION_END_POINT=https://<metadata-mcp-app>.azurewebsites.net/mcp
```

Resolution: `METADATA_EXTRACTION_END_POINT` → `METADATA_MCP_URL` → absent.

### 4. Invoke vs ask

| Path | Metadata MCP? |
|---|---|
| MAF `POST /invoke` | Yes — `{ "server": "metadata", "tool": "extract_metadata", "arguments": {…} }` |
| MAF `POST /ask` | **No** |
| Foundry Toolbox | **No** — Toolbox is chat-only |

Example job (via ip_api proxy or MAF directly):

```bash
curl -s http://127.0.0.1:8003/invoke \
  -H 'content-type: application/json' \
  -d '{
    "server": "metadata",
    "tool": "extract_metadata",
    "arguments": {"source_path": "blob://container/jobs/{job_id}/upload/file.pdf"}
  }'
```

Optional later: an `ip_api` REST route that calls MAF `/invoke` the same way
document jobs do. Do **not** call the metadata MCP URL from `ip_api`.

### 5. Azure JSON fill-in

Set `METADATA_EXTRACTION_END_POINT` (and optionally `METADATA_MCP_URL`) on the
**MAF** Web App. Leave empty until the metadata Web App exists.

### 6. Tests / smoke

```bash
cd central-agentic-flow
python -m pytest tests/test_maf_orchestrator.py -k "metadata_mcp or optional_chat"
```

---

## What not to do

- **Do not** put `http://127.0.0.1` or `localhost` in Azure JSON, `toolbox.yaml`,
  or any hosted Foundry setting.
- **Do not** put metadata (or document/voice) on `/ask` or a Foundry Toolbox.
  Jobs stay `modes: [jobs]` and `POST /invoke`.
- **Do not** put chat (or business) on `/invoke`. Ask servers stay `modes: [ask]`.
- **Do not** replace `BUSINESS_MCP_URL` with chat — they are siblings.
- **Do not** call MCP URLs from `ip_api`. Gateway → MAF only.
- **Do not** commit `.env`, Azure keys, SAS tokens, Foundry project endpoints,
  or Toolbox endpoints.

## Config files touched for these slots

| File | Role |
|---|---|
| `central-agentic-flow/config/mcp_registry.yml` | Optional `chat-agent` + `metadata-agent` entries |
| `central-agentic-flow/src/central_agentic_flow/mcp_registry.py` | URL helpers + aliases |
| `central-agentic-flow/config/azure-webapp.settings.json` | Empty keys until you fill HTTPS `/mcp` |
| `.env.example` and `central-agentic-flow/.env.example` | Commented local URLs |
