"""Admin template library: local filesystem backend, SQLAlchemy metadata."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_sample_template import build_sample_template
from ip_api.api.main import create_app
from ip_api.storage.template_store import DEFAULT_TEMPLATE_FOLDER

ADMIN_KEY = "test-admin-key"
HEADERS = {"X-Admin-Api-Key": ADMIN_KEY}
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FOLDER = DEFAULT_TEMPLATE_FOLDER


def _isolate_local(tmp_path: Path, monkeypatch, *, admin_key: str | None = ADMIN_KEY) -> Path:
    storage = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_BASE_PATH", str(storage))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "local")
    if admin_key is None:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ADMIN_API_KEY", admin_key)
    for key in (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_PASSWORD",
        "SQLALCHEMY_DATABASE_URL",
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_STORAGE_ACCOUNT_KEY",
        "AZURE_STORAGE_SAS_TOKEN",
        "AZURE_STORAGE_SAS_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    from ip_api.core.settings import reload_settings
    from ip_api.storage.blob_store import reset_blob_store
    from ip_api.storage.template_store import reset_template_store

    reload_settings()
    reset_template_store()
    reset_blob_store()
    return storage


@pytest.fixture
def admin_client(tmp_path: Path, monkeypatch):
    storage = _isolate_local(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        yield client, storage

    from ip_api.core.settings import reload_settings

    reload_settings()


def _upload(
    client: TestClient,
    tmp_path: Path,
    *,
    folder: str | None = FOLDER,
    name: str | None = None,
):
    docx = build_sample_template(tmp_path / "upload.docx").read_bytes()
    data: dict[str, str] = {}
    if folder is not None:
        data["folder_name"] = folder
    if name is not None:
        data["template_name"] = name
    return client.post(
        "/api/v1/admin/templates",
        headers=HEADERS,
        data=data,
        files={"file": ("contract_template.docx", docx, DOCX_TYPE)},
    )


def test_upload_stores_template_under_default_folder(admin_client, tmp_path: Path) -> None:
    client, storage = admin_client

    resp = _upload(client, tmp_path, folder=FOLDER, name="supply-contract")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["folder_name"] == FOLDER
    assert body["template_name"] == "supply-contract.docx"
    assert body["location"] == f"{FOLDER}/supply-contract.docx"
    assert body["storage_backend"] == "local"
    assert body["size_bytes"] > 0
    assert len(body["checksum_sha256"]) == 64
    assert (storage / "templates" / FOLDER / "supply-contract.docx").is_file()


def test_omitted_folder_name_defaults_to_ipp_default_template(
    admin_client, tmp_path: Path
) -> None:
    client, storage = admin_client

    body = _upload(client, tmp_path, folder=None, name="supply-contract").json()

    assert body["folder_name"] == FOLDER
    assert (storage / "templates" / FOLDER / "supply-contract.docx").is_file()


def test_template_name_defaults_to_uploaded_filename(admin_client, tmp_path: Path) -> None:
    client, storage = admin_client

    body = _upload(client, tmp_path).json()

    assert body["template_name"] == "contract_template.docx"
    assert (storage / "templates" / FOLDER / "contract_template.docx").is_file()


def test_reupload_replaces_the_same_location(admin_client, tmp_path: Path) -> None:
    client, _ = admin_client
    first = _upload(client, tmp_path, name="supply-contract").json()
    second = _upload(client, tmp_path, name="supply-contract").json()

    assert second["created_at"] == first["created_at"]
    assert second["location"] == first["location"]
    listing = client.get("/api/v1/admin/templates", headers=HEADERS).json()
    assert listing["count"] == 1


def test_list_filters_by_folder_and_reports_backend(admin_client, tmp_path: Path) -> None:
    client, _ = admin_client
    _upload(client, tmp_path, name="supply-contract")
    _upload(client, tmp_path, name="nda")

    listing = client.get("/api/v1/admin/templates", headers=HEADERS).json()
    assert listing["count"] == 2
    assert listing["storage_backend"] == "local"

    scoped = client.get(
        "/api/v1/admin/templates", headers=HEADERS, params={"folder_name": FOLDER}
    ).json()
    assert {row["location"] for row in scoped["templates"]} == {
        f"{FOLDER}/nda.docx",
        f"{FOLDER}/supply-contract.docx",
    }

    folders = client.get("/api/v1/admin/templates/folders", headers=HEADERS).json()
    assert folders == [FOLDER]


def test_dedicated_path_upload_and_list_by_folder(admin_client, tmp_path: Path) -> None:
    """POST/GET /admin/templates/{folder_name} — default folder ipp_pricing_default_template."""
    client, storage = admin_client
    docx = build_sample_template(tmp_path / "upload.docx").read_bytes()

    uploaded = client.post(
        f"/api/v1/admin/templates/{FOLDER}",
        headers=HEADERS,
        data={"template_name": "supply-contract"},
        files={"file": ("contract_template.docx", docx, DOCX_TYPE)},
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["location"] == f"{FOLDER}/supply-contract.docx"
    assert (storage / "templates" / FOLDER / "supply-contract.docx").is_file()

    listed = client.get(f"/api/v1/admin/templates/{FOLDER}", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["count"] == 1
    assert payload["templates"][0]["folder_name"] == FOLDER
    assert payload["templates"][0]["template_name"] == "supply-contract.docx"


def test_download_returns_the_stored_docx(admin_client, tmp_path: Path) -> None:
    client, _ = admin_client
    _upload(client, tmp_path, name="supply-contract")

    resp = client.get(
        f"/api/v1/admin/templates/{FOLDER}/supply-contract.docx/download", headers=HEADERS
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == DOCX_TYPE
    assert resp.content[:2] == b"PK"  # .docx is a zip container


def test_delete_removes_row_and_file(admin_client, tmp_path: Path) -> None:
    client, storage = admin_client
    _upload(client, tmp_path, name="supply-contract")

    resp = client.delete(
        f"/api/v1/admin/templates/{FOLDER}/supply-contract.docx", headers=HEADERS
    )

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert not (storage / "templates" / FOLDER / "supply-contract.docx").exists()
    assert client.get("/api/v1/admin/templates", headers=HEADERS).json()["count"] == 0


def test_missing_template_is_404(admin_client) -> None:
    client, _ = admin_client
    resp = client.get(f"/api/v1/admin/templates/{FOLDER}/nope.docx", headers=HEADERS)
    assert resp.status_code == 404


def test_non_docx_upload_is_rejected(admin_client) -> None:
    client, _ = admin_client
    resp = client.post(
        "/api/v1/admin/templates",
        headers=HEADERS,
        data={"folder_name": FOLDER},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_path_traversal_in_names_is_rejected(admin_client, tmp_path: Path) -> None:
    client, _ = admin_client
    docx = build_sample_template(tmp_path / "upload.docx").read_bytes()

    resp = client.post(
        "/api/v1/admin/templates",
        headers=HEADERS,
        data={"folder_name": "../escape", "template_name": "t.docx"},
        files={"file": ("t.docx", docx, DOCX_TYPE)},
    )

    assert resp.status_code == 400
    assert "path separators" in resp.json()["detail"]


def test_admin_routes_require_the_api_key(admin_client) -> None:
    client, _ = admin_client

    assert client.get("/api/v1/admin/templates").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/templates", headers={"X-Admin-Api-Key": "wrong"}
        ).status_code
        == 401
    )


def test_admin_routes_disabled_without_configured_key(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch, admin_key=None)
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/admin/templates", headers=HEADERS)
    assert resp.status_code == 503
    assert "ADMIN_API_KEY" in resp.json()["detail"]

    from ip_api.core.settings import reload_settings

    reload_settings()


def test_document_job_can_use_a_stored_template(admin_client, tmp_path: Path) -> None:
    """A job names the stored template instead of re-uploading the .docx."""
    client, storage = admin_client
    _upload(client, tmp_path, name="supply-contract")

    resp = client.post(
        "/api/v1/documents/jobs",
        data={
            "data": '{"invoice_number": "A-1"}',
            "folder_name": FOLDER,
            "template_name": "supply-contract",
        },
    )

    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    materialized = storage / "jobs" / job_id / "template.docx"
    assert materialized.is_file()
    assert materialized.read_bytes()[:2] == b"PK"


def test_document_job_defaults_folder_when_only_template_name_is_sent(
    admin_client, tmp_path: Path
) -> None:
    client, storage = admin_client
    _upload(client, tmp_path, name="supply-contract")

    resp = client.post(
        "/api/v1/documents/jobs",
        data={"data": '{"invoice_number": "A-1"}', "template_name": "supply-contract"},
    )

    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert (storage / "jobs" / job_id / "template.docx").is_file()


def test_document_job_rejects_both_upload_and_stored_template(
    admin_client, tmp_path: Path
) -> None:
    client, _ = admin_client
    _upload(client, tmp_path, name="supply-contract")
    docx = build_sample_template(tmp_path / "inline.docx").read_bytes()

    resp = client.post(
        "/api/v1/documents/jobs",
        data={
            "data": "{}",
            "folder_name": FOLDER,
            "template_name": "supply-contract",
        },
        files={"template": ("inline.docx", docx, DOCX_TYPE)},
    )

    assert resp.status_code == 400
    assert "not both" in resp.json()["detail"]


def test_document_job_requires_a_template(admin_client) -> None:
    client, _ = admin_client
    resp = client.post("/api/v1/documents/jobs", data={"data": "{}"})
    assert resp.status_code == 400
    assert "template is required" in resp.json()["detail"]


def test_document_job_with_unknown_stored_template_is_404(admin_client) -> None:
    client, _ = admin_client
    resp = client.post(
        "/api/v1/documents/jobs",
        data={"data": "{}", "folder_name": FOLDER, "template_name": "nope"},
    )
    assert resp.status_code == 404


def test_public_library_list_needs_no_admin_key(admin_client, tmp_path: Path) -> None:
    client, _ = admin_client
    _upload(client, tmp_path, name="gpo-pricing")
    resp = client.get("/api/v1/documents/templates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["folder_name"] == FOLDER
    assert FOLDER == "ipp_pricing_default_template"
    names = {row["template_name"] for row in body["templates"]}
    assert "gpo-pricing.docx" in names


def test_public_library_list_includes_docx_on_disk_without_sql(
    admin_client,
) -> None:
    client, storage = admin_client
    folder = storage / "templates" / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "from-blob-layout.docx").write_bytes(b"PK\x03\x04")
    body = client.get("/api/v1/documents/templates").json()
    assert (storage / "templates" / FOLDER / "from-blob-layout.docx").is_file()
    names = {row["template_name"] for row in body["templates"]}
    assert "from-blob-layout.docx" in names
