#!/usr/bin/env bash
# Install all local components.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  echo "Using: uv sync --all-packages"
  uv sync --all-packages
  echo "OK. Run: python run_all_components.py"
  exit 0
fi

echo "uv not found — using pip (do NOT use pip install -e . alone)"
echo "Using: pip install -r requirements-workspace.txt"
python -m pip install -U pip
python -m pip install -r requirements-workspace.txt
echo "OK. Run: python run_all_components.py"
