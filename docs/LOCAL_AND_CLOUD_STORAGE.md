# Local SQLite / local files vs Azure SQL / Blob

Every component runs against either backend pair without code changes. Two env
switches decide, independently:

| Concern | Local default | Azure | Switch |
|---|---|---|---|
| Metadata (SQL) | SQLite file | Azure SQL | `AZURE_SQL_SERVER` + `AZURE_SQL_PASSWORD`, or `SQLALCHEMY_DATABASE_URL` |
| Files (.docx, JSON, audio) | Filesystem under `STORAGE_BASE_PATH` | Blob container | `FILE_STORAGE_BACKEND` + `AZURE_STORAGE_*` |

All SQL goes through SQLAlchemy 2.x — no component uses `sqlite3`, `pyodbc`, or
`pymssql` directly, so the same ORM code serves both backends.

## Run everything locally

```bash
FILE_STORAGE_BACKEND=local
STORAGE_BASE_PATH=./data/storage
SQLITE_DATABASE_PATH=./data/app.db
ADMIN_API_KEY=local-dev-key
# leave AZURE_SQL_* and AZURE_STORAGE_* unset
```

Verify with the API health probe:

```bash
curl -s localhost:8000/api/v1/health | jq '{storage_backend, sqlite_database_path, azure_sql_server}'
# → { "storage_backend": "local", "sqlite_database_path": ".../app.db", "azure_sql_server": null }
```

`azure_sql_server: null` means the SQLAlchemy engine resolved to SQLite.

### Backend resolution order

`build_database_url()` (one copy per component, same logic):

1. explicit `SQLALCHEMY_DATABASE_URL`
2. `AZURE_SQL_SERVER` + `AZURE_SQL_PASSWORD` → `mssql+pyodbc` (or `mssql+pymssql`
   when `AZURE_SQL_DIALECT=pymssql`)
3. `sqlite:///$SQLITE_DATABASE_PATH`

File storage: `FILE_STORAGE_BACKEND` accepts `local` or `azure_blob` (aliases
`azure`, `blob`, `azureblob`). When unset it auto-selects `azure_blob` if any
Azure storage credential is present, otherwise `local`.

### One caveat for split local runs

In local mode the database stores absolute filesystem paths, so `ip_api` and
`document-processing-mcp` must see the same filesystem — same machine, or the
shared `app-data` volume that `docker-compose.yml` already mounts at
`/home/data`. Azure Blob is what makes truly isolated filesystems work, because
then paths are `blob://` refs instead.

## Who owns which tables

`ensure_schema()` creates only the tables a component owns, so components can
share one database without fighting over DDL.

| Component | Tables it creates |
|---|---|
| `ip_api` | all of them (job, accuracy, transcription, voice, call logs, sessions, `template_library`, LangGraph checkpoint tables) |
| `document-processing-mcp` | `job_table_document_mcp`, `accuracy_report_document_mcp`, `call_logs` |
| `voice_enable_mcp` | `voice_contracts`, `call_logs`, `lg_checkpoints`, `lg_checkpoint_blobs`, `lg_checkpoint_writes` |
| `central-agentic-flow` | `call_logs` |

Azure-SQL-only migrations (NVARCHAR widening and the Portal overview views) stay
in `ip_api` and `document-processing-mcp`, which own the document tables. They
are skipped entirely on SQLite.

Voice legal entities and pricelists are dummy HITL reference data read from
`samples/data/contract_catalog.json`, not SQL rows — so a fresh database needs no
seeding before the voice flow works.

Voice HITL graph state (pause/resume `thread_id`) defaults to
`lg_checkpoints` / `lg_checkpoint_blobs` / `lg_checkpoint_writes` in the same
SQLite or Azure SQL database — not in-process `MemorySaver`. Restarting the
voice MCP keeps a pending confirmation resumable.

To use Redis instead (vanilla Redis or Azure Cache — no RediSearch required):

```bash
LANGGRAPH_CHECKPOINT_BACKEND=redis
REDIS_URL=redis://127.0.0.1:6379/0
# optional TTL for abandoned HITL threads:
# LANGGRAPH_CHECKPOINT_REDIS_TTL_SECONDS=86400
```

Compose: `docker compose --profile redis up` then set `REDIS_URL=redis://redis:6379/0`
on `voice-enable-mcp`. Completed contracts stay in SQL either way.

## Admin template library

Upload a customer's Word template once, then submit jobs against it by name.
Templates land at `{customer_name}/{template_name}.docx` in whichever file
backend is configured:

| Backend | Location |
|---|---|
| local | `{STORAGE_BASE_PATH}/templates/{customer_name}/{template_name}.docx` |
| azure_blob | `{AZURE_BLOB_TEMPLATE_PREFIX}/{customer_name}/{template_name}.docx` in `AZURE_BLOB_CONTAINER` |

Metadata (`storage_ref`, size, SHA-256, uploader, timestamps) is a
`template_library` row, so listing works identically on both backends.

### Auth

Every admin route requires `X-Admin-Api-Key` to match `ADMIN_API_KEY`. With
`ADMIN_API_KEY` unset the router returns `503` for all requests, so an
unconfigured deployment cannot expose template writes.

### Routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/admin/templates` | Upload / replace (customer name in the form) |
| POST | `/api/v1/admin/templates/{customer_name}` | Dedicated upload into that customer's folder |
| GET | `/api/v1/admin/templates` | List (optional `?customer_name=`) |
| GET | `/api/v1/admin/templates/{customer_name}` | List templates for one customer |
| GET | `/api/v1/admin/templates/customers` | Distinct customer names |
| GET | `/api/v1/admin/templates/{customer_name}/{template_name}` | Metadata |
| GET | `/api/v1/admin/templates/{customer_name}/{template_name}/download` | Stored .docx bytes |
| DELETE | `/api/v1/admin/templates/{customer_name}/{template_name}` | Remove row + file |

### Upload

```bash
curl -X POST localhost:8000/api/v1/admin/templates/acme-corp \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  -F "template_name=supply-contract" \
  -F "file=@samples/templates/contract_template.docx"

curl -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  localhost:8000/api/v1/admin/templates/acme-corp
```

```json
{
  "customer_name": "acme-corp",
  "template_name": "supply-contract.docx",
  "location": "acme-corp/supply-contract.docx",
  "storage_backend": "local",
  "storage_ref": "/.../storage/templates/acme-corp/supply-contract.docx",
  "size_bytes": 67579,
  "checksum_sha256": "2efe5f82...",
  "download_url": "/api/v1/admin/templates/acme-corp/supply-contract.docx/download"
}
```

Naming rules:

- `template_name` is optional and defaults to the uploaded filename.
- The `.docx` suffix is enforced; the upload must be a `.docx` file.
- Names are single path segments. Anything containing `/`, `\`, `.` or `..` is
  rejected with `400` rather than silently rewritten, so a template never lands
  somewhere the caller did not ask for. Other unsupported characters collapse to
  `-` (`"Supply Contract v2"` → `Supply-Contract-v2.docx`).
- Re-uploading the same customer + template replaces the file and keeps the
  original `created_at`.

### Generate a document from a stored template

Pass `customer_name` + `template_name` instead of a `template` file:

```bash
curl -X POST localhost:8000/api/v1/documents/jobs \
  -F 'data={"contract_title":"Acme supply"}' \
  -F "customer_name=acme-corp" \
  -F "template_name=supply-contract"
```

The API copies the stored template into the job directory and the pipeline runs
unchanged. Sending both an upload and a stored-template name is a `400` — pick
one. Sending neither is also a `400`.

## Environment reference

| Variable | Default | Notes |
|---|---|---|
| `STORAGE_BASE_PATH` | `./data/storage` | Root for jobs, audio, templates |
| `SQLITE_DATABASE_PATH` | `{STORAGE_BASE_PATH}/../app.db` | Used unless Azure SQL is configured |
| `TEMPLATES_SUBDIRECTORY` | `templates` | Local template library folder |
| `AZURE_BLOB_TEMPLATE_PREFIX` | `templates` | Blob prefix for the template library |
| `ADMIN_API_KEY` | *(unset)* | Required to enable the admin routes |
| `FILE_STORAGE_BACKEND` | auto | `local` or `azure_blob` |
| `SQLALCHEMY_DATABASE_URL` | *(unset)* | Full override, wins over `AZURE_SQL_*` |
| `AZURE_SQL_DIALECT` | `pyodbc` | `pyodbc` or `pymssql` |
