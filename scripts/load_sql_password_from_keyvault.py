#!/usr/bin/env python3
"""Load ``AZURE_SQL_PASSWORD`` from Azure Key Vault.

Local (this script / run_all_components.py):
  1. If AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET are set, use
     that Entra app (no az login).
  2. Else use Azure CLI: run ``az login`` first (correct tenant).

Azure Web Apps do not use this script. Set a Key Vault *reference* on
AZURE_SQL_PASSWORD and grant the app managed identity Key Vault Secrets User.

Skip when the vault is not configured, or when ``AZURE_SQL_PASSWORD`` is already set.
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


def vault_url(vault_name: str) -> str:
    explicit = (os.getenv("AZURE_KEY_VAULT_URL") or os.getenv("AZURE_KEYVAULT_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    return f"https://{vault_name}.vault.azure.net"


def _service_principal_parts() -> tuple[str, str, str] | None:
    tenant = (os.getenv("AZURE_TENANT_ID") or "").strip()
    client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
    secret = (os.getenv("AZURE_CLIENT_SECRET") or "").strip()
    if tenant and client_id and secret:
        return tenant, client_id, secret
    return None


def _run_az(args: list[str]) -> str:
    az = shutil.which("az")
    if az is None:
        raise RuntimeError(
            "Azure CLI (`az`) is not on PATH. Install it, then run `az login` "
            "for the tenant that owns the Key Vault."
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


def _fetch_via_az(*, vault_name: str, secret_name: str) -> str:
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


def _fetch_via_sdk(*, vault_name: str, secret_name: str) -> str:
    from azure.identity import ClientSecretCredential
    from azure.keyvault.secrets import SecretClient

    tenant, client_id, secret = _service_principal_parts() or ("", "", "")
    credential = ClientSecretCredential(
        tenant_id=tenant, client_id=client_id, client_secret=secret
    )
    client = SecretClient(vault_url=vault_url(vault_name), credential=credential)
    try:
        value = (client.get_secret(secret_name).value or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(str(exc)) from exc
    if not value:
        raise RuntimeError(
            f"Key Vault secret '{secret_name}' in vault '{vault_name}' is empty"
        )
    return value


def fetch_sql_password(
    *,
    vault_name: str,
    secret_name: str = DEFAULT_SECRET_NAME,
) -> str:
    if _service_principal_parts():
        return _fetch_via_sdk(vault_name=vault_name, secret_name=secret_name)
    return _fetch_via_az(vault_name=vault_name, secret_name=secret_name)


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
        description="Fetch AZURE_SQL_PASSWORD from Azure Key Vault (az login, or Entra app)."
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
