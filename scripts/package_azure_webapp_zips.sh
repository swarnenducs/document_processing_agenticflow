#!/usr/bin/env bash
# Run each component's own package_azure_webapp.sh (each folder can be its own repo).
#
#   ./scripts/package_azure_webapp_zips.sh
#   ./scripts/package_azure_webapp_zips.sh api ui maf
#
# Copies each component zip to dist/azure-webapp/<name>.zip
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

folder_for() {
  case "$1" in
    ui) echo UI ;;
    api) echo ip_api ;;
    document) echo document-processing-mcp ;;
    voice) echo voice_enable_mcp ;;
    maf) echo central-agentic-flow ;;
    *) return 1 ;;
  esac
}

resolve_name() {
  key="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$key" in
    ui|ui-app) echo ui ;;
    api|ip_api|ip-api) echo api ;;
    document|document-processing-mcp|document-mcp) echo document ;;
    voice|voice_enable_mcp|voice-mcp) echo voice ;;
    maf|central-agentic-flow|central_agentic_flow) echo maf ;;
    *) echo "Unknown component: $1" >&2; return 2 ;;
  esac
}

NAMES=""
if [[ $# -eq 0 ]] || [[ "${1:-}" == "all" ]]; then
  NAMES="ui api document voice maf"
else
  for arg in "$@"; do
    NAMES="$NAMES $(resolve_name "$arg")"
  done
fi

OUT_DIR="$ROOT/dist/azure-webapp"
mkdir -p "$OUT_DIR"

for name in $NAMES; do
  folder="$(folder_for "$name")"
  script="$ROOT/$folder/package_azure_webapp.sh"
  chmod +x "$script"
  dest="$OUT_DIR/$name.zip"
  echo "==> $folder"
  "$script" "$dest"
done

echo
echo "Component scripts (use these after a repo split):"
echo "  UI/package_azure_webapp.sh"
echo "  ip_api/package_azure_webapp.sh"
echo "  document-processing-mcp/package_azure_webapp.sh"
echo "  voice_enable_mcp/package_azure_webapp.sh"
echo "  central-agentic-flow/package_azure_webapp.sh"
echo
echo "Copied zips: $OUT_DIR"
