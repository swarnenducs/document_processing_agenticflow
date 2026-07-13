"""FastAPI + SQLite storage tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from document_processing_agenticflow.api.main import create_app
from document_processing_agenticflow.core.settings import get_settings
from document_processing_agenticflow.storage.job_store import JobStore
from scripts.create_sample_template import build_sample_template


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    storage = tmp_path / "storage"
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("STORAGE_BASE_PATH", str(storage))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(db_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    import document_processing_agenticflow.api.routes as routes_mod
    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    routes_mod._store = None

    app = create_app()
    with TestClient(app) as client:
        yield client, storage, db_path

    settings_mod._settings = None
    routes_mod._store = None


def _sample_docx_bytes(tmp_path: Path) -> bytes:
    path = build_sample_template(tmp_path / "t.docx")
    return path.read_bytes()


def _sample_json() -> dict:
    return {
        "invoice_number": "API-001",
        "invoice_date": "2026-07-11",
        "customer": {"name": "API Co", "address": "1 API St", "email": "a@api.com"},
        "items": [
            {"description": "X", "quantity": 1, "unit_price": 10, "total": 10},
            {"description": "Y", "quantity": 2, "unit_price": 5, "total": 10},
        ],
        "subtotal": 20,
        "tax": 4,
        "total_amount": 24,
        "notes": "via API",
    }


def test_health(api_client) -> None:
    client, storage, db_path = api_client
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert storage.as_posix() in body["storage_base_path"]
    assert db_path.as_posix() in body["sqlite_database_path"]


def test_document_job_flow(api_client, tmp_path: Path) -> None:
    client, storage, _ = api_client
    docx_bytes = _sample_docx_bytes(tmp_path)
    data = _sample_json()

    resp = client.post(
        "/api/v1/documents/jobs",
        files={"template": ("template.docx", docx_bytes, "application/octet-stream")},
        data={"data": json.dumps(data), "skip_validation": "false"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = "pending"
    last_body = {}
    for _ in range(50):
        r = client.get(f"/api/v1/documents/jobs/{job_id}")
        assert r.status_code == 200
        last_body = r.json()
        status = last_body["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.1)

    assert status == "completed", last_body

    dl = client.get(f"/api/v1/documents/jobs/{job_id}/download")
    assert dl.status_code == 200

    out = tmp_path / "downloaded.docx"
    out.write_bytes(dl.content)
    doc = Document(out)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "API-001" in text

    job_dir = storage / "jobs" / job_id
    assert (job_dir / "template.docx").exists()
    assert (job_dir / "output.docx").exists()


def test_job_store_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "custom_storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "custom.db"))

    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    cfg = get_settings()
    assert cfg.storage_base_path == (tmp_path / "custom_storage").resolve()

    store = JobStore()
    jid, job_dir, _tpl, _data, _out = store.create_job_paths()
    assert job_dir == cfg.job_dir(jid)
    settings_mod._settings = None


def test_transcribe_requires_audio(api_client) -> None:
    client, _, _ = api_client
    resp = client.post("/api/v1/audio/transcribe")
    assert resp.status_code == 422
