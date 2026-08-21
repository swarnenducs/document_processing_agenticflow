"""Template library naming, path safety, and backend selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from ip_api.core.settings import reload_settings
from ip_api.storage.template_store import (
    TemplateNameError,
    normalize_template_name,
    sanitize_segment,
)


def _isolate(tmp_path: Path, monkeypatch, *, backend: str = "local") -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", backend)
    for key in ("AZURE_SQL_SERVER", "AZURE_SQL_PASSWORD", "SQLALCHEMY_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    reload_settings()


def test_template_name_always_gets_the_docx_suffix() -> None:
    assert normalize_template_name("supply-contract") == "supply-contract.docx"
    assert normalize_template_name("supply-contract.docx") == "supply-contract.docx"
    assert normalize_template_name("Supply Contract v2") == "Supply-Contract-v2.docx"


def test_path_separators_are_rejected_not_stripped() -> None:
    """Silently rewriting a traversal would store the file somewhere unexpected."""
    for bad in ("../escape", "a/b", "a\\b", "..", "."):
        with pytest.raises(TemplateNameError):
            sanitize_segment(bad, label="customer_name")


def test_empty_and_unusable_names_are_rejected() -> None:
    with pytest.raises(TemplateNameError):
        sanitize_segment("   ", label="customer_name")
    with pytest.raises(TemplateNameError):
        sanitize_segment("!!!", label="customer_name")


def test_local_backend_writes_under_the_templates_root(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    from ip_api.storage.template_store import TemplateStore

    store = TemplateStore()
    record = store.save(
        customer_name="Acme Corp", template_name="supply contract", content=b"docx-bytes"
    )

    assert record.customer_name == "Acme-Corp"
    assert record.location == "Acme-Corp/supply-contract.docx"
    assert record.storage_backend == "local"
    expected = tmp_path / "storage" / "templates" / "Acme-Corp" / "supply-contract.docx"
    assert Path(record.storage_ref) == expected
    assert store.read_bytes(record) == b"docx-bytes"


def test_materialize_copies_into_a_job_dir(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    from ip_api.storage.template_store import TemplateStore

    store = TemplateStore()
    record = store.save(customer_name="acme", template_name="nda", content=b"payload")

    dest = store.materialize(record, tmp_path / "jobs" / "j1" / "template.docx")

    assert dest.read_bytes() == b"payload"


def test_blob_backend_builds_a_templates_prefixed_ref(tmp_path: Path, monkeypatch) -> None:
    """Blob layout is templates/{customer}/{template}, separate from job blobs."""
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "acct")
    monkeypatch.setenv("AZURE_STORAGE_SAS_TOKEN", "sv=2024-11-04&sig=fake")
    _isolate(tmp_path, monkeypatch, backend="azure_blob")

    from ip_api.storage.blob_store import blob_name_for_template, get_blob_store
    from ip_api.storage.template_store import TemplateStore

    assert get_blob_store().enabled is True
    assert TemplateStore().backend == "azure_blob"
    assert blob_name_for_template("acme", "nda.docx") == "templates/acme/nda.docx"


def test_blob_template_prefix_is_configurable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AZURE_BLOB_TEMPLATE_PREFIX", "customer-templates")
    _isolate(tmp_path, monkeypatch)

    from ip_api.storage.blob_store import blob_name_for_template

    assert blob_name_for_template("acme", "nda.docx") == "customer-templates/acme/nda.docx"
