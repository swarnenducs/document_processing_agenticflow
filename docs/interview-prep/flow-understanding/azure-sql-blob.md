# Azure SQL + Blob for document processing

**SQLAlchemy / Azure SQL** = job metadata (status, blob refs, scores, sessions, traces).  
**Azure Blob** = template `.docx`, JSON data, and generated `.docx`.

```text
UI upload template.docx + JSON in the request (`data` form field)
        → ip_api saves local scratch
        → Azure Blob  container: docuploadsolution
              jobs/{job_id}/upload/template.docx
              jobs/{job_id}/upload/data.json
              jobs/{job_id}/download/{output}.docx
        → Azure SQL job_table_document_mcp row (pending + blob refs)
        → Document MCP generate_document(template_blob, data_blob, output_blob, job_id)
              → download blobs to local scratch
              → LangGraph mapper/validator
              → upload generated .docx
              → update job_table_document_mcp + accuracy_report_document_mcp
```

Blob upload/download lives in **both** `ip_api` and `document-processing-mcp` (same env keys).

**Who writes SQL**

- `ip_api` creates the pending `document_jobs` row and publishes WebSocket stages.
- Document MCP completes the row (and accuracy report) when `job_id` is passed — required when MAF calls MCP with no API job runner.
- If MCP cannot reach SQL, `ip_api` applies the MCP result as a fallback (`db_updated: false`).

## Configure `.env`

```bash
AZURE_SQL_SERVER=ipp-sql-serv.database.windows.net
AZURE_SQL_USER=adminsql
AZURE_SQL_PASSWORD=...          # not committed
AZURE_SQL_DATABASE=ipp-app-db
AZURE_SQL_DIALECT=pyodbc
AZURE_SQL_ODBC_DRIVER=ODBC Driver 18 for SQL Server

FILE_STORAGE_BACKEND=azure_blob
AZURE_BLOB_CONTAINER=docuploadsolution

# Account key (or connection string) AND SAS can be set together.
# Runtime uses SAS when SAS_URL or SAS_TOKEN is present; otherwise key / connection string.
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
AZURE_STORAGE_ACCOUNT_NAME=...
AZURE_STORAGE_ACCOUNT_KEY=...
AZURE_STORAGE_SAS_TOKEN=sv=...&sig=...
AZURE_STORAGE_SAS_URL=https://YOUR_ACCOUNT.blob.core.windows.net/docuploadsolution?sv=...&sig=...
```

Azure SQL `ipp-app-db` tables for document processing:

- `job_table_document_mcp` — document MCP job status + blob refs + JSON payloads (`mcp` = `document_process_mcp`)
- `accuracy_report_document_mcp` — score columns keyed by `job_id`
- `job_table_document_mcp_overview` — **use this in Azure Portal** (no large JSON columns)
- `accuracy_report_document_mcp_overview` — **use this in Azure Portal** (scores only)
- `call_logs` — xid traces
- `sessions` / `session_requests` — UI session
- `voice_contracts` / `transcription_jobs` — voice MCP (when those flows run)

Leftover catalog tables `legal_entities` and `pricelists` are dropped (voice catalog is JSON, not Azure SQL).

Azure Portal **Edit data** on the base tables hides `NVARCHAR(MAX)` JSON, so those grids look empty. Open the `*_overview` views (or `SELECT` the score columns) to see jobs and accuracy.
