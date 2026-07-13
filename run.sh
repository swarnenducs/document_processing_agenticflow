#!/usr/bin/env bash
# Start FastAPI + Gradio UI together (macOS / Linux).
# Prefers Python script; falls back to uv.
set -euo pipefail
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  exec python3 run_both.py "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python run_both.py "$@"
fi
if command -v uv >/dev/null 2>&1; then
  exec uv run doc-app "$@"
fi

echo "[ERROR] Neither python3 nor uv found on PATH." >&2
echo "  pip install -r requirements.txt && python3 run_both.py" >&2
exit 1
