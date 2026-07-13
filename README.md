# Document Processing Agentic Flow

LangGraph workspace (managed with **UV**) that turns a Word `.docx` template + JSON data into a new Word document while preserving the original Word XML styles — with **tool-wrapped steps**, **generator confidence scores**, and **two separate LLMs**.

**Interview / architecture walkthrough:** see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).  
**Deploy to Azure Web Apps (GitHub Actions CI/CD):** see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## Two separate LLMs (provider-injectable)

Mapper and validator are **independent roles**. Each can use a different provider via env
(`MAPPER_PROVIDER` / `VALIDATOR_PROVIDER`), or you can inject a custom builder in code with
`register_llm_provider(...)`.

Built-in providers: **`openai`**, **`azure_openai`** (alias `azure`), **`groq`**,
**`openai_compatible`** (Ollama / vLLM / Together / any OpenAI-style base URL).

### LLM #1 — Mapper (default: OpenAI)

| | |
|---|---|
| **Role** | Map JSON fields → Word template placeholders + table fills |
| **Provider** | `MAPPER_PROVIDER` (default `openai`) |
| **Model** | `MAPPER_MODEL` or `OPENAI_MODEL` / Azure deployment name |
| **Env** | Provider credentials (see `.env.example`) |
| **Tool** | `map_json_to_template` |
| **Output** | Per-field mappings + `table_fills` + confidence scores |

### LLM #2 — Validator / Critic (default: Groq)

| | |
|---|---|
| **Role** | Independently verify template vs generated doc vs JSON |
| **Provider** | `VALIDATOR_PROVIDER` (default `groq`) |
| **Model** | `VALIDATOR_MODEL` or `GROQ_VALIDATOR_MODEL` / Azure deployment |
| **Env** | Provider credentials (see `.env.example`) |
| **Tool** | `validate_documents` |
| **Output** | pass/fail, validation score, issue list |

Examples:

```env
# OpenAI mapper + Groq critic (default shape)
MAPPER_PROVIDER=openai
MAPPER_MODEL=gpt-5
OPENAI_API_KEY=sk-...
VALIDATOR_PROVIDER=groq
VALIDATOR_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=gsk-...

# Azure OpenAI for both roles
MAPPER_PROVIDER=azure_openai
MAPPER_MODEL=gpt-4o-deploy
VALIDATOR_PROVIDER=azure_openai
VALIDATOR_MODEL=gpt-4o-critic
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Local OpenAI-compatible (e.g. Ollama)
MAPPER_PROVIDER=openai_compatible
MAPPER_MODEL=llama3.1
MAPPER_BASE_URL=http://127.0.0.1:11434/v1
```

Inject a custom provider:

```python
from document_processing_agenticflow.services.llm_factory import register_llm_provider

register_llm_provider("my_vendor", lambda config, temperature=0: MyChatModel(...))
# then: MAPPER_PROVIDER=my_vendor
```

Without credentials for the selected provider, steps fall back to deterministic rules (still scored).

## Pipeline

```text
load_json → extract_styles → map_fields (LLM #1 OpenAI) → generate_docx → validate (LLM #2 Groq) → confidence
                              ↑________________ retry once if validation fails _________|
```

| Step | Tool | LLM |
|------|------|-----|
| 1 | `extract_word_styles` | — (deterministic) |
| 2 | `map_json_to_template` | **LLM #1** OpenAI `gpt-5` |
| 3 | `generate_styled_document` | — (XML rewrite, scored) |
| 4 | `validate_documents` | **LLM #2** Groq `openai/gpt-oss-120b` |
| 5 | `compute_confidence_report` | — (aggregates both LLM scores) |

## Setup (UV)

```bash
uv sync
cp .env.example .env   # add your OPENAI_API_KEY + GROQ_API_KEY
```

For plain `pip` installs (Azure zip deploy, CI without UV), use the exported lock files:

```bash
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # runtime + pytest/ruff
# regenerate after dependency changes:
uv export --no-dev --no-hashes --output-file requirements.txt
uv export --group dev --no-hashes --output-file requirements-dev.txt
```

Prefer **`uv sync`** locally; `uv.lock` is the source of truth.

### `.env` layout (provider-injectable roles)

```env
# LLM #1 — Mapper
MAPPER_PROVIDER=openai          # openai | azure_openai | groq | openai_compatible
MAPPER_MODEL=gpt-5
OPENAI_API_KEY=sk-...

# LLM #2 — Validator
VALIDATOR_PROVIDER=groq
VALIDATOR_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=gsk-...

# Azure example (optional):
# MAPPER_PROVIDER=azure_openai
# MAPPER_MODEL=gpt-4o-deploy
# AZURE_OPENAI_API_KEY=...
# AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
# AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

See `.env.example` for the full matrix.

## Sample files

| File | Description |
|------|-------------|
| `samples/templates/invoice_template.docx` | Simple invoice demo template |
| `samples/data/invoice.json` | Invoice JSON |
| `samples/templates/contract_template.docx` | **Contract Template** example (Word) |
| `samples/data/dummy_products.json` | **dummy products** JSON (`DATE`, `accountName`, `products[]`) |
| `samples/data/contract_full.json` | Same content as `dummy_products.json` (alias) |

## Create sample template & run

```bash
uv run python scripts/create_sample_template.py

# Invoice example
uv run doc-agent \
  --template samples/templates/invoice_template.docx \
  --data samples/data/invoice.json \
  --output samples/output/invoice_filled.docx \
  --dump-extraction samples/output/extraction.json \
  --dump-mapping samples/output/mapping.json \
  --dump-confidence samples/output/confidence.json

# Contract example (Contract Template + dummy products)
uv run doc-agent \
  --template samples/templates/contract_template.docx \
  --data samples/data/dummy_products.json \
  --output samples/output/contract_filled.docx
```

CLI prints **LLM #1 (mapper)** and **LLM #2 (validator)** separately in the confidence report.

Useful flags:

- `--skip-validation` — skip LLM #2 critic step
- `--max-retries 1` — re-run map→generate if validation fails
- `--validation-threshold 0.7`
- `--fail-on-validation` — non-zero exit when critic rejects the doc

## Tools (agent mode)

All steps are LangChain tools via `get_document_tools()`:

```python
from document_processing_agenticflow.tools import get_document_tools
from document_processing_agenticflow.agent import run_agent

tools = get_document_tools()

# Orchestrator uses LLM #1 (OpenAI); tools call LLM #2 (Groq) for validation
run_agent(
  "Fill samples/templates/invoice_template.docx using samples/data/invoice.json "
  "and write samples/output/agent_out.docx, then validate and report confidence."
)
```

LLM wiring is centralized in `services/llm_factory.py`.

## Confidence score

All scores are exposed as **percentages** in `scores_pct` (API / Gradio / CLI).

```text
overall = 0.40*mapping + 0.25*coverage + 0.15*integrity + 0.20*validation
```

| Score | Meaning |
|-------|---------|
| Placeholder mapping % | LLM #1 confidence finding/mapping placeholders |
| Placeholder coverage % | Share of placeholders that got a mapping |
| Table mapping % | LLM #1 confidence on table header → JSON field |
| Generation integrity % | Deterministic checks after write |
| Validation % | LLM #2 critic score on template vs output vs JSON |
| Overall % | Weighted combination |

Report also includes:
- `mapper_llm` / `validator_llm`
- per-placeholder confidence %
- per-table-column confidence %
- validation pass/fail + issues

## Project layout

```text
src/document_processing_agenticflow/
  graph.py
  agent.py                 # orchestrator (LLM #1)
  tools.py
  cli.py
  models/
  nodes/pipeline.py
  services/
    llm_factory.py         # ← separate mapper vs validator LLM config
    pipeline_runner.py     # API background job runner
    speech_to_text.py      # voice → NL text
    style_extractor.py
    field_mapper.py        # LLM #1
    document_generator.py
    document_validator.py  # LLM #2
    confidence.py
  api/                     # FastAPI REST API
  storage/                 # SQLite + file paths
  core/settings.py         # env-based paths
samples/  scripts/  tests/
```

## Template placeholders (token syntax only)

The pipeline detects placeholder **syntax** (not hardcoded field names):

- `{{field}}` / `{{nested.path}}`
- `${field}`
- `«field»`
- `<DATE>` / `<ACCOUNT NAME>` (angle brackets)

**LLM #1 decides the meaning:** it reads the template text + table headers + your JSON and produces:

1. Scalar mappings (placeholder → JSON path + value)
2. `table_fills` plans (which JSON array fills which table, and which header maps to which object field)

There is **no hardcoded product/date synonym dictionary** in the happy path.  
Exact-name rules are used only when the configured **mapper** provider has no credentials.

## Tests

```bash
uv run pytest
```

Tests exercise offline generation with manual mappings (no live API keys required). Mapper/validator require LLMs at runtime.

## FastAPI + storage

### Storage model

```text
SQLite (job metadata)     →  SQLITE_DATABASE_PATH  (default: ./data/app.db)
Filesystem (blob files)   →  STORAGE_BASE_PATH     (default: ./data/storage)
  └── jobs/{job_id}/
        template.docx
        data.json
        output.docx
  └── audio/{transcription_id}/
        input.wav
```

All paths are configurable via `.env`.

### Start API server

```bash
uv run doc-api
# docs: http://localhost:8000/docs
```

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health + configured storage paths |
| `POST` | `/api/v1/documents/jobs` | Upload `.docx` + JSON → async LangGraph job (`202`) |
| `GET` | `/api/v1/documents/jobs/{job_id}` | Job status, confidence, validation |
| `GET` | `/api/v1/documents/jobs/{job_id}/download` | Download generated `.docx` |
| `DELETE` | `/api/v1/documents/jobs/{job_id}` | Delete job + files |
| `POST` | `/api/v1/audio/transcribe` | Voice/audio → natural language text |
| `GET` | `/api/v1/audio/transcriptions/{id}` | Retrieve past transcription |

### Example: generate document

```bash
curl -X POST http://localhost:8000/api/v1/documents/jobs \
  -F "template=@samples/templates/invoice_template.docx" \
  -F "data=@samples/data/invoice.json;type=application/json"

curl http://localhost:8000/api/v1/documents/jobs/{job_id}
curl -O http://localhost:8000/api/v1/documents/jobs/{job_id}/download
```

### Example: voice → text

```bash
curl -X POST http://localhost:8000/api/v1/audio/transcribe \
  -F "audio=@recording.wav" \
  -F "language=en"
```

Speech provider: `SPEECH_PROVIDER=openai` (Whisper) or `groq` (`whisper-large-v3`).

## Gradio UI

Web UI with **microphone recording** → sends audio to the FastAPI transcribe endpoint.

### Run (two terminals)

```bash
# Terminal 1 — API backend
uv run doc-api

# Terminal 2 — Gradio UI
uv run doc-ui
```

**Or start everything with one command:**

```bash
# Cross-platform (recommended if run.bat fails)
python run_both.py
# Windows also:
py -3 run_both.py

# Wrappers
./run.sh          # macOS / Linux
run.bat           # Windows CMD
.\run.ps1         # Windows PowerShell
uv run doc-app    # via UV entry point
```

Install deps first if needed:

```bash
uv sync
# or
pip install -r requirements.txt
```

Options:

```bash
python run_both.py --api-only    # FastAPI only
python run_both.py --ui-only     # Gradio only (API must already be running)
python run_both.py --no-wait     # Skip health check before UI
python run_both.py --use-uv      # Force child processes via `uv run`
uv run doc-app --api-only
```

Open **http://127.0.0.1:7860**

| Tab | What it does |
|-----|----------------|
| **Generate Document** (1st) | **Upload** `.docx` template + **upload** `.json` (or paste JSON) → poll job → download result |
| **Voice → Text** (2nd) | Record **or upload** audio → transcribe API → show transcript |

Both tabs use the same two-column layout: inputs on the left, results on the right.  
Sample buttons load:
- Invoice: `samples/templates/invoice_template.docx` + `samples/data/invoice.json`
- Contract: `samples/templates/contract_template.docx` + `samples/data/dummy_products.json`

UI env vars:

```env
API_BASE_URL=http://127.0.0.1:8000
GRADIO_HOST=127.0.0.1
GRADIO_PORT=7860
```

### Storage env vars

```env
STORAGE_BASE_PATH=./data/storage
SQLITE_DATABASE_PATH=./data/app.db
JOBS_SUBDIRECTORY=jobs
AUDIO_SUBDIRECTORY=audio
MAX_UPLOAD_MB=25
API_HOST=0.0.0.0
API_PORT=8000
SPEECH_PROVIDER=openai
OPENAI_WHISPER_MODEL=whisper-1
GROQ_WHISPER_MODEL=whisper-large-v3
```
