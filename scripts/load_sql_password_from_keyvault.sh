#!/usr/bin/env bash
# Load AZURE_SQL_PASSWORD from Azure Key Vault into the current shell.
#
#   source scripts/load_sql_password_from_keyvault.sh
#   python run_all_components.py
#
# `python run_all_components.py` already does this when AZURE_KEY_VAULT_NAME
# (or AZURE_KEY_VAULT_URL) is set in .env. Source this only for a one-off
# component run that does not go through that launcher.
#
# Requires: az login, Key Vault Secrets User on your account.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Source this script so the password stays in your shell:" >&2
  echo "  source scripts/load_sql_password_from_keyvault.sh" >&2
  echo "Or just run: python run_all_components.py (it loads the vault itself)." >&2
  exit 2
fi

if [[ -n "${AZURE_SQL_PASSWORD:-}" ]]; then
  echo "AZURE_SQL_PASSWORD is already set; skipping Key Vault." >&2
  return 0 2>/dev/null || exit 0
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

PASSWORD="$("$PYTHON" "$ROOT/scripts/load_sql_password_from_keyvault.py" --stdout)"
export AZURE_SQL_PASSWORD="$PASSWORD"
echo "AZURE_SQL_PASSWORD is set from Key Vault (not printed)." >&2
