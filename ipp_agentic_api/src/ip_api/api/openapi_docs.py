"""OpenAPI / Swagger copy for ipp_agentic_api (ip_api package)."""

from __future__ import annotations

APP_TITLE = "ipp_agentic_api"
APP_VERSION = "0.1.0"

APP_DESCRIPTION = """
**ipp_agentic_api** is the HTTP gateway for document generation, voice contracts,
speech-to-text, and chat.

This process does **not** run LangGraph itself. It accepts files and JSON, stores
state, then calls **MAF** (`CENTRAL_AGENT_END_POINT`, default port **8003**).
MAF calls **document MCP** (port **8001**) and **voice MCP** (port **8002**).

| Page | URL |
| --- | --- |
| Swagger UI | `/docs` |
| ReDoc | `/redoc` |
| OpenAPI JSON | `/openapi.json` |

---

## Which route to use

Use **`/api/v1/documents/*`** and **`/api/v1/voice/*`** from UIs and Postman.

`/api/v1/agents/*` is the same work via MAF tools, but it needs **file paths on the
MCP host** — not browser uploads.

MCP **`/mcp`** ports are not REST and are not listed in this schema.

| Goal | Call |
| --- | --- |
| Health | `GET /api/v1/health` |
| Create Word job | `POST /api/v1/documents/jobs` (multipart) |
| List library templates | `GET /api/v1/documents/templates` (default folder `ipp_pricing_default_template`) |
| Job status | `GET /api/v1/documents/jobs/{job_id}` |
| Download Word | `GET /api/v1/documents/jobs/{job_id}/download` |
| Accuracy JSON | `GET /api/v1/documents/jobs/{job_id}/accuracy` |
| Accuracy PDF | `GET /api/v1/documents/jobs/{job_id}/accuracy.pdf` |
| Live progress | WebSocket `.../documents/jobs/{job_id}/ws` |
| Start voice contract | `POST /api/v1/voice/contract` |
| Confirm voice HITL | `POST /api/v1/voice/contract/confirm` |
| Chat | `POST /api/ask` |
| Admin templates | `/api/v1/admin/templates` |
| Admin master data | `/api/v1/admin/master-data` |

---

## Headers

All of these are **optional** except the admin key on admin routes.

| Header | When |
| --- | --- |
| `X-Request-ID` or `X-Correlation-ID` | Correlation **xid**. Echoed on the response. Generated if omitted. |
| `X-Session-Id` | Reuse a session; otherwise the API may create one. |
| `X-User-Id` / `X-User-Email` | Optional identity stored with the session. |
| `X-Admin-Api-Key` | **Required** on `/api/v1/admin/*`. Must match env `ADMIN_API_KEY`. If that env is empty, admin returns **503**. |

---

## Document jobs

### Step 1 — Create the job

`POST /api/v1/documents/jobs`

Content type: **`multipart/form-data`** (not JSON).

| Form field | Required | Meaning |
| --- | --- | --- |
| `data` | Yes | JSON **object as a string**, not a file. Example: `{"party":"AVC"}` |
| `template` | One of template / template_name | Upload a `.docx` file |
| `template_name` | One of template / template_name | Name already in the admin library |
| `folder_name` | No | Library folder. Default: `ipp_pricing_default_template` |

### Step 2 — Read the 202 body

HTTP **202**. Keep these fields:

| Field | Meaning |
| --- | --- |
| `job_id` | Id for status, download, and WebSocket |
| `status_url` | `GET` this for status |
| `download_url` | `GET` this after `status` is `completed` |
| `ws_url` | **Path only** (example: `/api/v1/documents/jobs/{job_id}/ws`) |

Build the socket URL as `ws://<api-host>` + `ws_url`. On HTTPS APIs use `wss://`.

### Step 3 — Wait until the job finishes

Pick **one**:

1. **Long-poll (simplest)**  
   `GET /api/v1/documents/jobs/{job_id}?wait=true&timeout=180`  
   until `status` is `completed` or `failed`.

2. **WebSocket (live stages, for Angular / UIs)**  
   Connect to `ws://<host>/api/v1/documents/jobs/{job_id}/ws`.  
   The client **only receives** JSON. It does not send messages.  
   Each event looks like:

   ```json
   {
     "job_id": "...",
     "stage": "fields_mapped",
     "message": "Fields mapped from JSON",
     "progress": 0.55,
     "terminal": false
   }
   ```

   Close the socket when `terminal` is `true`, or `stage` is `completed` / `failed`.  
   If the socket drops, use the long-poll URL from step 3.1.

Swagger **Try it out** cannot open WebSockets. Use a browser, Angular, or a WS client.

### Step 4 — Download the Word file

Only when `status` is `completed`:

`GET /api/v1/documents/jobs/{job_id}/download`

If the job is still running, this returns **409**.

Voice HITL is **REST only** (no WebSocket). Browser UIs need `CORS_ORIGINS` for HTTP;
WebSockets do not use CORS.

---

## Voice contracts

1. `POST /api/v1/voice/contract` with JSON:

   ```json
   {
     "transcript": "create contract with legal entity AVC contract reference CR-1001"
   }
   ```

2. If the response includes `thread_id` and needs confirmation:

   `POST /api/v1/voice/contract/confirm`

   ```json
   {
     "legal_entity": "AVC",
     "contract_reference_number": "CR-1001",
     "thread_id": "<from start response>",
     "user_text": "yes"
   }
   ```

3. List or download: `GET /api/v1/voice/contracts` and
   `GET /api/v1/voice/contracts/{contract_id}/download`.

Speech only (no contract): `POST /api/v1/audio/transcribe`.  
Speech then start: `POST /api/v1/voice/contract/from-audio`.

---

## Storage

- **SQL:** SQLite locally unless Azure SQL env is set.
- **Files on this gateway:** `FILE_STORAGE_BACKEND` = `local` or `azure_blob`.
- **Voice contract files:** voice MCP disk (not Blob).

---

## Postman

Import `postman/IPP.postman_collection.json` and
`postman/local.postman_environment.json` (copies also under `ipp_agentic_api/postman/`).
Do not put secrets in the collection.
"""

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "health",
        "description": "Readiness: SQL, Blob, mapper/validator LLMs, speech, MAF, MCP catalogue.",
    },
    {
        "name": "documents",
        "description": (
            "Create a job (multipart), wait or WebSocket, then download the `.docx`. "
            "See the page overview for the four-step sequence."
        ),
    },
    {
        "name": "traces",
        "description": "HTTP/tool/LLM logs grouped by correlation **xid**.",
    },
    {
        "name": "audio",
        "description": "Speech-to-text only (Whisper via OpenAI or Groq). Does not create a contract.",
    },
    {
        "name": "voice",
        "description": (
            "Contract HITL via MAF → voice MCP. Start from text or audio, confirm, list, download. REST only."
        ),
    },
    {
        "name": "mcp-agents",
        "description": (
            "Thin proxies: FastAPI → MAF `/invoke`. Document generate needs existing "
            "`template_path` / `data_path` on the MCP host — not multipart upload."
        ),
    },
    {
        "name": "admin",
        "description": (
            "Word template library and master-data blocks (legal/sales notice text). "
            "Header `X-Admin-Api-Key` = `ADMIN_API_KEY`. "
            "Jobs can then send `template_name` instead of uploading a file."
        ),
    },
    {
        "name": "maf",
        "description": (
            "Chat proxy: `POST /api/ask` → MAF `/ask`. Send `Prompt` + `Persona` "
            "(persona LLM prompt file). Needs MAF running. "
            "Deterministic jobs still use `/api/v1/documents` and `/api/v1/voice`."
        ),
    },
]
