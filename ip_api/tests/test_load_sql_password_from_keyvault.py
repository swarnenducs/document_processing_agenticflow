"""Local Key Vault SQL password loader (Azure CLI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.load_sql_password_from_keyvault import (
    apply_sql_password_from_keyvault,
    vault_name_from_env,
)


@pytest.fixture(autouse=True)
def _isolate_vault_env(monkeypatch):
    monkeypatch.setattr(
        "scripts.load_sql_password_from_keyvault._load_root_env", lambda: None
    )
    for key in (
        "AZURE_SQL_PASSWORD",
        "AZURE_KEY_VAULT_NAME",
        "AZURE_KEY_VAULT_URL",
        "AZURE_KEYVAULT_URL",
        "AZURE_SQL_PASSWORD_SECRET_NAME",
    ):
        monkeypatch.delenv(key, raising=False)


def test_vault_name_from_url() -> None:
    assert (
        vault_name_from_env(url="https://ipp-kv.vault.azure.net/") == "ipp-kv"
    )
    assert vault_name_from_env(name="ipp-kv") == "ipp-kv"


def test_skip_when_password_already_set(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "already")
    monkeypatch.setenv("AZURE_KEY_VAULT_NAME", "ipp-kv")
    assert apply_sql_password_from_keyvault() is False
    assert os.environ["AZURE_SQL_PASSWORD"] == "already"


def test_skip_when_vault_not_configured() -> None:
    assert apply_sql_password_from_keyvault() is False
    assert not os.getenv("AZURE_SQL_PASSWORD")


def test_fetch_sets_password(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_KEY_VAULT_NAME", "ipp-kv")
    monkeypatch.setattr(
        "scripts.load_sql_password_from_keyvault._run_az",
        lambda args: "from-vault",
    )
    assert apply_sql_password_from_keyvault() is True
    assert os.environ["AZURE_SQL_PASSWORD"] == "from-vault"


def test_fetch_failure_exits(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_KEY_VAULT_NAME", "ipp-kv")

    def _fail(*, vault_name, secret_name):
        raise RuntimeError("az login required")

    monkeypatch.setattr("scripts.load_sql_password_from_keyvault.fetch_sql_password", _fail)
    with pytest.raises(SystemExit) as raised:
        apply_sql_password_from_keyvault()
    assert raised.value.code == 1
    assert not os.getenv("AZURE_SQL_PASSWORD")


def test_run_az_missing_cli(monkeypatch) -> None:
    monkeypatch.setattr("scripts.load_sql_password_from_keyvault.shutil.which", lambda _: None)
    monkeypatch.setenv("AZURE_KEY_VAULT_NAME", "ipp-kv")
    with pytest.raises(SystemExit):
        apply_sql_password_from_keyvault()
