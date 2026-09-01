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

In the **gitignored** `.env`, comment Azure SQL and Blob so `python ./run_all_components.py` uses SQLite + local files. Exact keys: [ENVIRONMENT.md](ENVIRONMENT.md#run-locally-sqlite--local-files).

```bash
FILE_STORAGE_BACKEND=local
STORAGE_BASE_PATH=./data/storage
SQLITE_DATABASE_PATH=./data/app.db
ADMIN_API_KEY=local-dev-key
# comment/unset:
#   SQLALCHEMY_DATABASE_URL
#   AZURE_SQL_SERVER  AZURE_SQL_PASSWORD
#   AZURE_KEY_VAULT_NAME  AZURE_KEY_VAULT_URL
#   AZURE_STORAGE_CONNECTION_STRING  AZURE_STORAGE_ACCOUNT_NAME
#   AZURE_STORAGE_ACCOUNT_KEY  AZURE_STORAGE_SAS_TOKEN  AZURE_STORAGE_SAS_URL
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

### Local: SQL password from Key Vault

This is the **local Azure SQL** path, not SQLite. Leave `AZURE_SQL_PASSWORD` empty and set the vault plus `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`. `python run_all_components.py` fetches the secret with the Azure SDK (no `az login`). If you instead want SQLite, **unset the vault name/URL and `AZURE_SQL_SERVER`** — otherwise the launcher injects the password and you stay on Azure SQL.

On **Azure Web Apps**, do not use this script. Set `AZURE_SQL_PASSWORD` to a Key Vault **reference** (see [DYNACONF.md](DYNACONF.md)). Paste the example JSON from each component’s `config/azure-webapp.settings.json`.

```bash
AZURE_SQL_SERVER=YOUR_SQL.database.windows.net
AZURE_SQL_USER=adminsql
AZURE_SQL_DATABASE=ipp-app-db
AZURE_KEY_VAULT_NAME=YOUR-VAULT
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
# AZURE_SQL_PASSWORD_SECRET_NAME=azure-sql-password   # default
# AZURE_SQL_PASSWORD=                                 # leave empty
```

For a shell that is not started by that launcher:

```bash
# macOS / Linux
source scripts/load_sql_password_from_keyvault.sh
```

```powershell
# Windows PowerShell
. .\scripts\load_sql_password_from_keyvault.ps1
python run_all_components.py
# or: .\run.ps1
```

The password is exported into the process environment only. It is not written to
`.env`. The Entra app needs **Key Vault Secrets User** on the vault.

Azure SQL still needs your client IP allowed on the server firewall.

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
| `ip_api` | all of them (job, accuracy, transcription, voice, call logs, sessions, `template_library`, `master_data`, LangGraph checkpoint tables) |
| `document-processing-mcp` | `job_table_document_mcp`, `accuracy_report_document_mcp`, `call_logs`, `master_data` |
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

Upload a Word template once into the default library folder
`ipp_default_template`, then submit jobs against it by name. Templates land at
`{folder_name}/{template_name}.docx` in whichever file backend is configured:

| Backend | Location |
|---|---|
| local | `{STORAGE_BASE_PATH}/templates/ipp_default_template/{template_name}.docx` |
| azure_blob | `{AZURE_BLOB_TEMPLATE_PREFIX}/ipp_default_template/{template_name}.docx` in `AZURE_BLOB_CONTAINER` |

Metadata (`storage_ref`, size, SHA-256, uploader, timestamps) is a
`template_library` row, so listing works identically on both backends.

### Auth

Every admin route requires `X-Admin-Api-Key` to match `ADMIN_API_KEY`. With
`ADMIN_API_KEY` unset the router returns `503` for all requests, so an
unconfigured deployment cannot expose template writes.

### Routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/admin/templates` | Upload / replace (`folder_name` form field, default `ipp_default_template`) |
| POST | `/api/v1/admin/templates/{folder_name}` | Dedicated upload; pass `ipp_default_template` |
| GET | `/api/v1/admin/templates` | List (optional `?folder_name=ipp_default_template`) |
| GET | `/api/v1/admin/templates/{folder_name}` | List templates in that folder |
| GET | `/api/v1/admin/templates/folders` | Distinct folder names |
| GET | `/api/v1/admin/templates/{folder_name}/{template_name}` | Metadata (`storage_ref` is `blob://…` on Azure) |
| GET | `/api/v1/admin/templates/{folder_name}/{template_name}/download` | Stored .docx bytes |
| DELETE | `/api/v1/admin/templates/{folder_name}/{template_name}` | Remove row + file |
| POST | `/api/v1/admin/master-data` | Add or replace a legal/sales block (`placeholder_key` + `content`) |
| GET | `/api/v1/admin/master-data` | List blocks (`?category=legal`) |
| GET | `/api/v1/admin/master-data/{placeholder_key}` | One block |
| PUT | `/api/v1/admin/master-data/{placeholder_key}` | Update content |
| DELETE | `/api/v1/admin/master-data/{placeholder_key}` | Remove row |

### Upload

```bash
curl -X POST localhost:8000/api/v1/admin/templates/ipp_default_template \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  -F "template_name=supply-contract" \
  -F "file=@samples/templates/contract_template.docx"

curl -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  localhost:8000/api/v1/admin/templates/ipp_default_template
```

```bash
curl -X POST localhost:8000/api/v1/admin/master-data \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"placeholder_key":"Legal_Department_Master_Data","category":"legal","content":"Legal Department\n200 Connell Drive, Suite 1000\nBerkeley Heights, NJ 07922\nE-mail: pmo@ABCTec.com","active":true}'
```

```json
{
  "folder_name": "ipp_default_template",
  "template_name": "supply-contract.docx",
  "location": "ipp_default_template/supply-contract.docx",
  "storage_backend": "local",
  "storage_ref": "/.../storage/templates/ipp_default_template/supply-contract.docx",
  "size_bytes": 67579,
  "checksum_sha256": "2efe5f82...",
  "download_url": "/api/v1/admin/templates/ipp_default_template/supply-contract.docx/download"
}
```

Naming rules:

- `folder_name` defaults to `ipp_default_template` when omitted.
- `template_name` is optional and defaults to the uploaded filename.
- The `.docx` suffix is enforced; the upload must be a `.docx` file.
- Names are single path segments. Anything containing `/`, `\`, `.` or `..` is
  rejected with `400` rather than silently rewritten, so a template never lands
  somewhere the caller did not ask for. Other unsupported characters collapse to
  `-` (`"Supply Contract v2"` → `Supply-Contract-v2.docx`).
- Re-uploading the same folder + template replaces the file and keeps the
  original `created_at`.

### Generate a document from a stored template

Pass `template_name` instead of a `template` file. `folder_name` defaults to
`ipp_default_template` if omitted:

```bash
curl -X POST localhost:8000/api/v1/documents/jobs \
  -F 'data={"contract_title":"Acme supply"}' \
  -F "folder_name=ipp_default_template" \
  -F "template_name=supply-contract"
```

The API copies the stored template into the job directory and the pipeline runs
unchanged. Sending both an upload and a stored-template name is a `400` — pick
one. Sending neither is also a `400`.

Environment reference: [ENVIRONMENT.md](ENVIRONMENT.md). Dynaconf later / Web App JSON: [DYNACONF.md](DYNACONF.md).

Storage-related keys:

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
| `AZURE_KEY_VAULT_NAME` | *(unset)* | Local `az` loader only: fetch `AZURE_SQL_PASSWORD` |
| `AZURE_KEY_VAULT_URL` | *(unset)* | Alternate to vault name (`https://<vault-name>.vault.azure.net/`) |
| `AZURE_SQL_PASSWORD_SECRET_NAME` | `azure-sql-password` | Key Vault secret name (local script + Azure reference) |
| `DOCUMENT_MAX_RETRIES` | `1` | Judge retry cap (0–3). API form `max_retries` overrides |
| `DOCUMENT_VALIDATION_THRESHOLD` | `0.7` | Judge accuracy bar 0–1 (`DOCUMENT_ACCURACY_THRESHOLD` alias) |
| `DOCUMENT_LLM_OPTIMIZATION_ENABLED` | `false` | Turn on mapper optimisation for all jobs unless the request sets `optimized_flow=false` |
| `DOCUMENT_MARKER_SYNTHESIS_ENABLED` | `true` | Unmarked Word files: LLM stamps placeholders. `false` = tagged templates only |
| `DOCUMENT_LLM_OPTIMIZATION_CONFIG` | `document-processing-mcp/config/llm_optimization.json` | JSON used only when optimisation is on |
