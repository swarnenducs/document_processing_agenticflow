#!/usr/bin/env python3
"""Load ``AZURE_SQL_PASSWORD`` from Azure Key Vault via the Azure CLI.

Used locally. App Service should use Key Vault references instead.

Skip (keep SQLite) when the vault is not configured.
Skip when ``AZURE_SQL_PASSWORD`` is already set.
Fetch when ``AZURE_KEY_VAULT_NAME`` or ``AZURE_KEY_VAULT_URL`` is set
and the password is empty.

  python run_all_components.py
  source scripts/load_sql_password_from_keyvault.sh
  python scripts/load_sql_password_from_keyvault.py --stdout
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_SECRET_NAME = "azure-sql-password"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_root_env() -> None:
    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=False)


def vault_name_from_env(
    *,
    name: str | None = None,
    url: str | None = None,
) -> str | None:
    raw_name = (name if name is not None else os.getenv("AZURE_KEY_VAULT_NAME") or "").strip()
    if raw_name:
        return raw_name
    raw_url = (
        url
        if url is not None
        else (
            os.getenv("AZURE_KEY_VAULT_URL")
            or os.getenv("AZURE_KEYVAULT_URL")
            or ""
        )
    ).strip()
    if not raw_url:
        return None
    host = urlparse(raw_url).netloc or raw_url
    host = host.split("/")[0]
    if host.endswith(".vault.azure.net"):
        return host[: -len(".vault.azure.net")].rstrip(".")
    return host.split(".")[0] or None


def secret_name_from_env() -> str:
    return (os.getenv("AZURE_SQL_PASSWORD_SECRET_NAME") or DEFAULT_SECRET_NAME).strip() or (
        DEFAULT_SECRET_NAME
    )


def _run_az(args: list[str]) -> str:
    az = shutil.which("az")
    if az is None:
        raise RuntimeError(
            "Azure CLI (`az`) is not on PATH. Install it, then run `az login`."
        )
    result = subprocess.run(
        [az, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"
        raise RuntimeError(detail)
    return (result.stdout or "").strip()


def fetch_sql_password(
    *,
    vault_name: str,
    secret_name: str = DEFAULT_SECRET_NAME,
) -> str:
    value = _run_az(
        [
            "keyvault",
            "secret",
            "show",
            "--vault-name",
            vault_name,
            "--name",
            secret_name,
            "--query",
            "value",
            "-o",
            "tsv",
        ]
    )
    if not value:
        raise RuntimeError(
            f"Key Vault secret '{secret_name}' in vault '{vault_name}' is empty"
        )
    return value


def apply_sql_password_from_keyvault(*, strict: bool = True) -> bool:
    """Set ``AZURE_SQL_PASSWORD`` from Key Vault when configured.

    Returns True when a secret was fetched. Returns False when skipped.
    Raises SystemExit on fetch failure if ``strict`` is True.
    """
    _load_root_env()
    existing = (os.getenv("AZURE_SQL_PASSWORD") or "").strip()
    if existing:
        return False
    vault = vault_name_from_env()
    if not vault:
        return False
    secret = secret_name_from_env()
    try:
        password = fetch_sql_password(vault_name=vault, secret_name=secret)
    except RuntimeError as error:
        message = (
            f"Failed to load AZURE_SQL_PASSWORD from Key Vault '{vault}' "
            f"secret '{secret}': {error}"
        )
        if strict:
            print(message, file=sys.stderr)
            raise SystemExit(1) from error
        raise
    os.environ["AZURE_SQL_PASSWORD"] = password
    print(
        f"Loaded AZURE_SQL_PASSWORD from Key Vault '{vault}' secret '{secret}'",
        file=sys.stderr,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch AZURE_SQL_PASSWORD from Azure Key Vault (Azure CLI)."
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the password only (for: export AZURE_SQL_PASSWORD=\"$(... --stdout)\")",
    )
    args = parser.parse_args(argv)
    _load_root_env()

    existing = (os.getenv("AZURE_SQL_PASSWORD") or "").strip()
    if existing:
        if args.stdout:
            print(existing, end="")
        else:
            print("AZURE_SQL_PASSWORD is already set; skipping Key Vault.", file=sys.stderr)
        return 0

    if not vault_name_from_env():
        print(
            "Set AZURE_KEY_VAULT_NAME or AZURE_KEY_VAULT_URL to fetch the SQL password.",
            file=sys.stderr,
        )
        return 2

    try:
        apply_sql_password_from_keyvault(strict=False)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    password = os.environ["AZURE_SQL_PASSWORD"]
    if args.stdout:
        print(password, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
