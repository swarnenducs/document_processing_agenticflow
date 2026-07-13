#!/usr/bin/env bash
# Start FastAPI + Gradio UI together.
# Usage:
#   ./run.sh
#   ./run.sh --api-only
#   ./run.sh --ui-only

set -euo pipefail
cd "$(dirname "$0")"
exec uv run doc-app "$@"
