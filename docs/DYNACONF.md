# Dynaconf, env overlay, and SettingsDep

This repo’s **local vs Azure SQL / Blob switch is env-only today**. No code change is required to pick SQLite vs Azure SQL, or local files vs Blob. Dynaconf (and later Pydantic `BaseSettings`) can sit in front of the same keys without renaming them.

**Never commit `.env`**, Azure keys, SAS tokens, Foundry/toolbox endpoints, SQL passwords, or Key Vault secret *values*.

Related: [ENVIRONMENT.md](ENVIRONMENT.md), [LOCAL_AND_CLOUD_STORAGE.md](LOCAL_AND_CLOUD_STORAGE.md), per-component Azure Web App JSON (see [Apply Azure Web App JSON](#apply-azure-web-app-json)).

---

## Today (API, MAF, document MCP, voice MCP)

1. **Dynaconf** loads component `.env` then repo-root `.env` (`envvar_prefix=False`, no `DYNACONF_` prefix). It copies values into `os.environ` **only when the key is missing**, so Azure App Settings and the local launcher win.
2. **Pydantic `BaseSettings`** reads those env vars. FastAPI still injects `SettingsDep` in `ip_api`. MAF and both MCPs keep `settings()` / `reload_settings()`.
3. **UI** still uses dotenv + dataclass (Gradio-only; no Azure SQL/Blob switch in that package).

SQLAlchemy URL resolution (`build_database_url()` in each `storage/db.py`):

1. `SQLALCHEMY_DATABASE_URL` if set
2. else `AZURE_SQL_SERVER` **and** `AZURE_SQL_PASSWORD` → Azure SQL (`mssql+pyodbc` or `mssql+pymssql`)
3. else SQLite at `SQLITE_DATABASE_PATH`

Blob resolution (`FILE_STORAGE_BACKEND`, ip_api and document MCP):

- `local` or `azure_blob` (aliases `azure`, `blob`, `azureblob`)
- if unset: `azure_blob` when any `AZURE_STORAGE_*` credential is present, otherwise `local`

`python run_all_components.py` (via `ip_api.run_app`) also calls `scripts/load_sql_password_from_keyvault.py` **before** children start: if `AZURE_SQL_PASSWORD` is empty and `AZURE_KEY_VAULT_NAME` or `AZURE_KEY_VAULT_URL` is set, it fills the password with `SecretClient` + `ClientSecretCredential` (`AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`). That is a **local** convenience, not App Service.

Inter-component hops use the **same** overlay: fill `CENTRAL_AGENT_END_POINT` (API → MAF), `TEMPLATE_PROCESSING_END_POINT` (MAF → document MCP), and `VOICE_PROCESSING_END_POINT` (MAF → voice MCP). Optional: `CHAT_MCP_END_POINT` (ask) and `METADATA_EXTRACTION_END_POINT` (jobs). Older names `MAF_BASE_URL` / `MAF_URL`, `DOCUMENT_MCP_URL`, `VOICE_MCP_URL`, `CHAT_MCP_URL`, and `METADATA_MCP_URL` stay as aliases. Dynaconf later reads those keys with `envvar_prefix=False` — no `DYNACONF_` prefix and no rename. Local `.env` keeps `127.0.0.1`; Azure JSON uses `https://<app>.azurewebsites.net` placeholders (optional MCP keys stay empty until you have those apps). Details: [ENVIRONMENT.md](ENVIRONMENT.md#inter-component-urls-fill-per-environment).

---

## Path

```
local:   .env  →  Dynaconf (fill missing keys)  →  Pydantic BaseSettings  →  settings() / SettingsDep
Azure:   Web App Application settings (process env)  →  Dynaconf skips those keys  →  same BaseSettings
```

`settings()`, `reload_settings()`, and (in ip_api) `get_settings_dependency()` / `SettingsDep` are unchanged for callers.

Do **not** require a `DYNACONF_` prefix. `envvar_prefix=False` so `AZURE_SQL_SERVER` stays `AZURE_SQL_SERVER`.

| Package | Loader | Settings |
|---|---|---|
| ip_api | `ipp_agentic_api/src/ip_api/core/dynaconf_loader.py` | `ipp_agentic_api/src/ip_api/core/settings.py` |
| central-agentic-flow | `central-agentic-flow/src/central_agentic_flow/core/dynaconf_loader.py` | `.../core/settings.py` |
| document-processing-mcp | `document-processing-mcp/src/document_processing_mcp/core/dynaconf_loader.py` | `.../core/settings.py` |
| voice_enable_mcp | `voice_enable_mcp/src/voice_enable_mcp/core/dynaconf_loader.py` | `.../core/settings.py` |

---

## Layer order (keep env on top)

When Dynaconf is added, use this overlay so local and Azure stay “set the same keys”:

| Priority (highest last) | Source | When |
|---|---|---|
| 1 | Code defaults / optional `settings.toml` | Checked-in non-secrets |
| 2 | Component `.env` then root `.env` | Local only (gitignored) |
| 3 | Process environment | Shell exports, `run_all_components.py`, **Azure Web App Application settings** |

Azure App Settings **are** process environment variables. After Dynaconf, they still win over files. No second switch and no `ENV_FOR_DYNACONF=production` requirement for SQL vs SQLite.

---

## Key Vault

| Where | How `AZURE_SQL_PASSWORD` is supplied | What this repo does |
|---|---|---|
| **Local SQLite** | Do not set it. Also unset `AZURE_SQL_SERVER` and vault name/URL so the launcher cannot inject a password into an Azure SQL path. | SQLite at `SQLITE_DATABASE_PATH` |
| **Local Azure SQL** | Leave `AZURE_SQL_PASSWORD` empty. Set `AZURE_KEY_VAULT_NAME` (or `AZURE_KEY_VAULT_URL`), `AZURE_SQL_SERVER`, and `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`. | `scripts/load_sql_password_from_keyvault.py` (default secret `azure-sql-password`) |
| **Azure Web App** | Application setting value is a **Key Vault reference**. App Service (managed identity) resolves it **before** the process starts. | App sees a normal `AZURE_SQL_PASSWORD` string. Do **not** commit the password. Do **not** set `AZURE_KEY_VAULT_NAME` on the Web App for this purpose — that name is for the local `az` loader only. |

Reference form (placeholders only; replace `<vault-name>`):

```text
@Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/azure-sql-password/)
```

Equivalent:

```text
@Microsoft.KeyVault(VaultName=<vault-name>;SecretName=azure-sql-password)
```

Default secret name in scripts: `AZURE_SQL_PASSWORD_SECRET_NAME` → `azure-sql-password`.

The Web App’s managed identity needs **Key Vault Secrets User** (get) on that vault. Locally, an Entra **app registration** (`AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`) needs the same role. `az login` is not used.

---

## Will the current SQL/Blob switch still work?

**Yes.** The switch is “are these env vars set?” Dynaconf with `envvar_prefix=False` and Azure App Settings both populate the **same** names. `build_database_url()` does not care whether dotenv, Dynaconf, or App Service wrote them.

Unset on local SQLite (and local files): see [ENVIRONMENT.md](ENVIRONMENT.md#run-locally-sqlite--local-files).

---

## Apply Azure Web App JSON

Committed **examples** (no real secrets). Portal Advanced edit format: `{name, value, slotSetting}`.

| Component | Port | File |
|---|---|---|
| UI | `:7860` | [`UI/config/azure-webapp.settings.json`](../UI/config/azure-webapp.settings.json) |
| ip_api | `:8000` | [`ipp_agentic_api/config/azure-webapp.settings.json`](../ipp_agentic_api/config/azure-webapp.settings.json) |
| document-processing-mcp | `:8001` | [`document-processing-mcp/config/azure-webapp.settings.json`](../document-processing-mcp/config/azure-webapp.settings.json) |
| voice_enable_mcp | `:8002` | [`voice_enable_mcp/config/azure-webapp.settings.json`](../voice_enable_mcp/config/azure-webapp.settings.json) |
| central-agentic-flow | `:8003` | [`central-agentic-flow/config/azure-webapp.settings.json`](../central-agentic-flow/config/azure-webapp.settings.json) |

### Portal

App Service → **Environment variables** (or Configuration) → **App settings** → **Advanced edit** → paste the JSON array. Replace every `<placeholder>`.

### Azure CLI

The committed files are the **Portal Advanced edit** array (`name` / `value` / `slotSetting`). `az webapp config appsettings set --settings @file.json` does **not** reliably accept that array. The CLI wants `NAME=VALUE` arguments. Quote any value that starts with `@` so the CLI does not treat it as a filename.

```bash
az webapp config appsettings set -g <rg> -n <app> --settings \
  WEBSITES_PORT=8000 \
  API_HOST=0.0.0.0 \
  'AZURE_SQL_PASSWORD=@Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/azure-sql-password/)'
```

To apply a whole example file, flatten then pass `--settings` (do not print the output if you have already replaced placeholders with real secrets):

```bash
python3 -c "import json,sys; print(' '.join(x['name']+'='+x['value'] for x in json.load(open(sys.argv[1]))))" \
  ipp_agentic_api/config/azure-webapp.settings.json
# Review, replace placeholders, then:
az webapp config appsettings set -g <rg> -n <app> --settings <flattened NAME=VALUE...>
```

Replace `<vault-name>`, `<rg>`, `<app>`, and every hostname placeholder before applying.

Hop URLs to fill (same names Dynaconf will overlay; preferred name first):

| Component JSON | Preferred | Alias you can omit if the preferred name is set |
|---|---|---|
| `ipp_agentic_api/config/azure-webapp.settings.json` | `CENTRAL_AGENT_END_POINT=https://<maf-app>.azurewebsites.net` | `MAF_BASE_URL` |
| `central-agentic-flow/config/azure-webapp.settings.json` | `TEMPLATE_PROCESSING_END_POINT=https://<document-mcp-app>.azurewebsites.net/mcp` | `DOCUMENT_MCP_URL` |
| same | `VOICE_PROCESSING_END_POINT=https://<voice-mcp-app>.azurewebsites.net/mcp` | `VOICE_MCP_URL` |
| same | `CHAT_MCP_END_POINT=` (optional ask MCP; fill `https://<chat-mcp-app>.azurewebsites.net/mcp`) | `CHAT_MCP_URL` |
| same | `METADATA_EXTRACTION_END_POINT=` (optional jobs MCP; fill `https://<metadata-mcp-app>.azurewebsites.net/mcp`) | `METADATA_MCP_URL` |

