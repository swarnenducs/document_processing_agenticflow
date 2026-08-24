# API details

Consolidated catalogue of every public HTTP / WebSocket route and MCP tool
in this repo. Storage follows `FILE_STORAGE_BACKEND` (`local` or `azure_blob`)
and SQL follows SQLAlchemy (SQLite locally, Azure SQL when `AZURE_SQL_*` is set).

Default hosts:

| Service | Port | Base |
|---|---|---|
| Gateway (`ip_api`) | 8000 | `http://127.0.0.1:8000` |
| Document MCP | 8001 | `http://127.0.0.1:8001/mcp` |
| Voice MCP | 8002 | `http://127.0.0.1:8002/mcp` |
| MAF orchestrator | 8003 | `http://127.0.0.1:8003` |
| UI (Gradio) | 7860 | `http://127.0.0.1:7860` |

Interactive OpenAPI: `http://127.0.0.1:8000/docs`.

Postman collection (gateway + MAF): [POSTMAN.md](POSTMAN.md).

**Counts**

| Surface | Count |
|---|---|
| Gateway HTTP | 34 |
| Gateway WebSocket | 1 |
| MAF HTTP | 6 |
| Document MCP tools | 2 |
| Voice MCP tools | 4 |

---

## Common headers (gateway)

Set on every `ip_api` request; echoed on the response.

| Header | Purpose |
|---|---|
| `X-Request-ID` / `X-Correlation-ID` | Correlation `xid` (minted if omitted) |
| `X-Session-Id` | Client session (created if omitted) |
| `X-User-Id` | Optional user id |
| `X-User-Email` | Optional user email |
| `X-Admin-Api-Key` | Required on all `/api/v1/admin/*` routes |

---

## A. Gateway — health and chat

### `GET /api/v1/health`

Liveness plus configured storage, SQL, blob, mapper, validator, speech, MCP, MAF.

**Response (`HealthResponse`):** `status`, `storage_backend` (`local` \| `azure_blob`), `storage_base_path`, `sqlite_database_path`, `azure_sql_*`, `azure_blob_*`, LLM/speech flags, `document_mcp_available`, `voice_mcp_available`, `maf_available`, `maf_base_url`.

### `POST /api/ask`

Natural-language chat. Proxies to MAF `POST /ask`. Business MCP tools only when `BUSINESS_MCP_URL` is set; document/voice jobs are **not** chat tools.

**JSON body:** `{ "message": "...", "instructions"?, "session_id"?, "user_id"?, "user_email"? }`

**Response:** `{ "ok", "text", "response_id", "orchestrator": "maf", "session_id", "user_id", "user_email" }`

### `GET /api/ask/health`

Proxies MAF `/ask/health` (chat client + MCP catalogue).

---

## B. Gateway — document jobs (auto template)

Template + JSON → filled `.docx`. Files land on local disk or Azure Blob.

### `POST /api/v1/documents/jobs` → `202`

Start a job. Provide **either** an uploaded `.docx` **or** a stored library template.

**Form fields**

| Field | Required | Notes |
|---|---|---|
| `data` | yes | JSON object as a form string (not a file) |
| `template` | one of | `.docx` upload |
| `template_name` | one of | Reuse an admin-library template |
| `folder_name` | no | Library folder; default `ipp_default_template` |
| `skip_validation` | no | default `false` |
| `max_retries` | no | Map→generate retries. Omit to use `DOCUMENT_MAX_RETRIES` (or JSON retries when `optimized_flow` is on) |
| `validation_threshold` | no | Judge accuracy bar 0–1. Omit to use `DOCUMENT_VALIDATION_THRESHOLD` |
| `optimized_flow` | no | Use `llm_optimization.json` mapper cascade. Default: `DOCUMENT_LLM_OPTIMIZATION_ENABLED` |
| `session_id` / `user_id` / `user_email` | no | |

**Response (`JobAcceptedResponse`):** `job_id`, `xid`, `session_id`, `status: pending`, `status_url`, `download_url`, `ws_url`.

Sending both an upload and a stored-template name is `400`. Sending neither is `400`.

### `GET /api/v1/documents/jobs`

List recent jobs (`?limit=50`, max 200). Newest first.

### `GET /api/v1/documents/jobs/{job_id}`

Job status, scores, accuracy snapshot.

**Query:** `wait=true` long-polls until `completed`/`failed`; `timeout` 1–600s (default 180).

**Response (`JobStatusResponse`):** `status`, paths, `confidence`, `validation`, `scores_pct`, `elapsed_ms` / `elapsed`, `download_url` (when ready), `accuracy_report`.

### `GET /api/v1/documents/jobs/{job_id}/accuracy`

Dedicated accuracy row from `accuracy_report_document_mcp`.

**404** if the job exists but no report yet, or if the job id is unknown.

Typical fields: `overall_confidence_pct`, extraction/mapping/coverage/generation scores, `extraction_passed`, `validation_passed`, LLM names, `notes`, JSON blobs, elapsed.

### `GET /api/v1/documents/jobs/{job_id}/download`

Returns the generated `.docx` only (`Content-Type` Word OOXML).

**409** if status is not `completed`. Resolves local path or blob ref.

### `DELETE /api/v1/documents/jobs/{job_id}` → `204`

Deletes the SQL row and job files / blob prefix.

### `WS /api/v1/documents/jobs/{job_id}/ws`

Live pipeline stages (`accepted`, extraction, mapped, validated, `completed` / `failed`). In-process hub (no Redis). Closes after a terminal event.

---

## C. Gateway — admin default templates

All routes require `X-Admin-Api-Key` matching `ADMIN_API_KEY`. Unset key → **503**. Wrong key → **401**.

Layout: `{folder_name}/{template_name}.docx` under `STORAGE_BASE_PATH/templates/` or blob prefix `AZURE_BLOB_TEMPLATE_PREFIX` (default `templates`). The default folder is `ipp_default_template`.

### `POST /api/v1/admin/templates` → `201`

Upload. `folder_name` in the form defaults to `ipp_default_template`.

**Form:** `file` (`.docx`), optional `folder_name` (`ipp_default_template`), optional `template_name`, `uploaded_by`.

### `POST /api/v1/admin/templates/{folder_name}` → `201`

Dedicated folder upload. Pass `ipp_default_template` in the path.

Re-upload of the same folder + name replaces the file and keeps `created_at`.

**Response (`TemplateRecordResponse`):** `folder_name`, `location` (`ipp_default_template/supply-contract.docx`), `storage_backend`, `storage_ref` (`blob://…` on Azure), `size_bytes`, `checksum_sha256`, `download_url`.

Path separators (`/`, `\`, `..`) in names → **400**.

### `GET /api/v1/admin/templates`

List all (`?folder_name=` optional filter, `?limit=`).

### `GET /api/v1/admin/templates/{folder_name}`

List templates in one folder (pass `ipp_default_template`).

**Response:** `{ "count", "storage_backend", "templates": [...] }`

### `GET /api/v1/admin/templates/folders`

Distinct folder names, sorted.

### `GET /api/v1/admin/templates/{folder_name}/{template_name}`

One template’s metadata.

### `GET /api/v1/admin/templates/{folder_name}/{template_name}/download`

Stored `.docx` bytes (local or blob). **410** if the row exists but the file is gone.

### `DELETE /api/v1/admin/templates/{folder_name}/{template_name}`

Removes the SQL row and the file/blob.

---

## D. Gateway — traces

### `GET /api/v1/traces/{xid}`

HTTP / tool / LLM call logs plus jobs for one correlation id.

**Response:** `{ "xid", "job_count", "log_count", "jobs", "logs" }`

---

## E. Gateway — audio and voice contracts

### `POST /api/v1/audio/transcribe`

Speech-to-text. Audio file + optional `language`, `provider` (`auto` \| `openai` \| `groq`).

**Response:** `transcription_id`, `text`, `provider`, `model`, `language`.

### `GET /api/v1/audio/transcriptions/{transcription_id}`

Persisted transcription row.

### `POST /api/v1/voice/contract`

Start create-contract from already-transcribed text. Proxies MAF → voice MCP.

**JSON:** `{ "transcript", "auto_create"?, "session_id"? }`

May return `status: needs_confirmation` plus `thread_id`, `legal_entity`, `candidates`.

### `POST /api/v1/voice/contract/confirm`

Resume HITL (`thread_id` + `legal_entity` + `contract_reference_number`).

### `POST /api/v1/voice/contract/from-audio`

Transcribe audio, then start the voice-contract flow.

### `GET /api/v1/voice/contracts`

List saved voice contracts (`?limit=`).

### `GET /api/v1/voice/contracts/{contract_id}`

One saved contract (payload, entity, pricelist, file path).

### `GET /api/v1/voice/contracts/{contract_id}/download?format=docx|txt`

Dummy contract file produced by the voice flow.

---

## F. Gateway — agent proxies (via MAF `/invoke`)

Thin JSON wrappers. Prefer the document-job and voice routes above for file uploads.

| Method | Path | Forwards to |
|---|---|---|
| `GET` | `/api/v1/agents/health` | MAF MCP catalogue |
| `GET` | `/api/v1/agents/tools` | All MAF-registered tools |
| `GET` | `/api/v1/agents/document/tools` | Document MCP tools |
| `POST` | `/api/v1/agents/document/generate` | `document` / `generate_document` (paths or blob refs, not a file upload) |
| `GET` | `/api/v1/agents/voice/tools` | Voice MCP tools |
| `POST` | `/api/v1/agents/voice/contract` | `voice` / `start_voice_contract` |
| `POST` | `/api/v1/agents/voice/contract/confirm` | `voice` / `confirm_voice_contract` |

`POST /api/v1/agents/document/generate` body: `template_path`, `data_path` or `data_json`, optional `output_path`, `job_id`, `xid`, validation flags.

---

## G. MAF orchestrator (`:8003`)

Clients normally go through the gateway. ip_api uses these internally.

| Method | Path | Details |
|---|---|---|
| `GET` | `/health` | `{ "ok": true, "service": "maf" }` |
| `GET` | `/ask/health` | Chat client + MCP catalogue |
| `GET` | `/mcps` | Registered MCP servers |
| `GET` | `/tools` | Same catalogue as `/mcps` |
| `POST` | `/ask` | Conversational turn (business tools only) |
| `POST` | `/invoke` | Deterministic tool call: `{ "server", "tool", "arguments", "xid"? }` |

`POST /invoke` is jobs-only (document + voice). Chat cannot reach those tools.

Foundry-hosted chat uses the Responses protocol (`foundry_main.py`), not these FastAPI routes.

---

## H. MCP tools (not REST)

Called by MAF over streamable HTTP (`/mcp`). JSON object results.

### Document MCP (`document_process_mcp`)

| Tool | Args | Result |
|---|---|---|
| `health` | — | `ok`, blob/SQL flags |
| `generate_document` | `template_path`, `data_path` or `data_json`, optional `output_path`, `job_id`, `xid`, validation flags | `GenerateDocumentResponse` (status, output path/ref, confidence, scores) |

### Voice MCP (`voice_process_mcp`)

| Tool | Args | Result |
|---|---|---|
| `health` | — | liveness |
| `start_voice_contract` | `transcript`, `auto_create?` | may be `needs_confirmation` |
| `confirm_voice_contract` | `legal_entity`, `contract_reference_number`, `thread_id?`, `user_text?` | completed contract + `contract_id` |
| `list_voice_contracts` | `limit?` | saved rows |

---

## Typical call sequences

**Auto template (upload each time)**

1. `POST /api/v1/documents/jobs` (`template` + `data`)
2. Optional `WS .../ws` or `GET .../{job_id}?wait=true`
3. `GET .../{job_id}/accuracy`
4. `GET .../{job_id}/download`

**Auto template (reuse default library)**

1. `POST /api/v1/admin/templates/ipp_default_template` (once)
2. `GET /api/v1/admin/templates/ipp_default_template`
3. `POST /api/v1/documents/jobs` with `folder_name=ipp_default_template` + `template_name` + `data`
4. accuracy + download as above

**Chat**

1. `POST /api/ask` `{ "message": "..." }`

**Voice HITL**

1. `POST /api/v1/voice/contract` or `/from-audio`
2. If `needs_confirmation` → `POST /api/v1/voice/contract/confirm`
3. `GET /api/v1/voice/contracts/{id}/download`
