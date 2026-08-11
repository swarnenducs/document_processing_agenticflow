#!/usr/bin/env bash
# Regenerate per-component + consolidated requirements from pyproject extras.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p requirements

echo "Exporting requirements/document-mcp.txt ..."
uv export --extra document --no-hashes --no-emit-project -o requirements/document-mcp.txt

echo "Exporting requirements/voice-mcp.txt ..."
uv export --extra voice --no-hashes --no-emit-project -o requirements/voice-mcp.txt

echo "Exporting requirements/maf.txt ..."
uv export --extra maf --no-hashes --no-emit-project -o requirements/maf.txt

echo "Exporting requirements/api.txt ..."
uv export --extra api --no-hashes --no-emit-project -o requirements/api.txt

echo "Exporting requirements/ui.txt ..."
uv export --extra ui --no-hashes --no-emit-project -o requirements/ui.txt

echo "Exporting requirements-dev.txt (all-components + dev) ..."
uv export --extra all-components --group dev --no-hashes -o requirements-dev.txt

# Keep root requirements.txt aligned with API+workers common local install (all-components without pinning the editable twice)
echo "Exporting requirements.txt (all-components) ..."
uv export --extra all-components --no-hashes -o requirements.txt

echo "Done."
