"""FastAPI + SQLite storage tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ip_api.api.main import create_app
from ip_api.core.settings import get_settings
from ip_api.storage.job_store import JobStore
from api_sample_template import build_sample_template


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    storage = tmp_path / "storage"
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("STORAGE_BASE_PATH", str(storage))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "local")
    monkeypatch.delenv("AZURE_SQL_SERVER", raising=False)
    monkeypatch.delenv("AZURE_SQL_PASSWORD", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_KEY", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_SAS_TOKEN", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_SAS_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    from ip_api.core.settings import reload_settings

    reload_settings()

    app = create_app()
    with TestClient(app) as client:
        yield client, storage, db_path

    reload_settings()


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
    assert body["status"] in {"ok", "degraded"}
    assert "mapper_available" in body
    assert "validator_available" in body
    assert "document_mcp_available" in body
    assert "voice_mcp_available" in body
    assert isinstance(body["document_mcp_available"], bool)
    assert isinstance(body["voice_mcp_available"], bool)
    assert storage.as_posix() in body["storage_base_path"]
    assert db_path.as_posix() in body["sqlite_database_path"]


def test_document_job_requires_json_in_request(api_client, tmp_path: Path) -> None:
    """JSON must be the form field `data`, not a file upload."""
    client, _, _ = api_client
    docx_bytes = _sample_docx_bytes(tmp_path)

    missing = client.post(
        "/api/v1/documents/jobs",
        files={"template": ("template.docx", docx_bytes, "application/octet-stream")},
        data={"skip_validation": "true"},
    )
    assert missing.status_code == 422

    as_file = client.post(
        "/api/v1/documents/jobs",
        files={
            "template": ("template.docx", docx_bytes, "application/octet-stream"),
            "data_json": ("payload.json", json.dumps(_sample_json()).encode(), "application/json"),
        },
        data={"skip_validation": "true"},
    )
    assert as_file.status_code == 422


def test_document_job_fails_without_mapper_llm(api_client, tmp_path: Path) -> None:
    """Without live LLM credentials, jobs must fail (no rule fallback)."""
    client, storage, _ = api_client
    docx_bytes = _sample_docx_bytes(tmp_path)
    data = _sample_json()

    resp = client.post(
        "/api/v1/documents/jobs",
        files={"template": ("template.docx", docx_bytes, "application/octet-stream")},
        data={"data": json.dumps(data), "skip_validation": "true"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = "pending"
    last_body: dict = {}
    for _ in range(50):
        r = client.get(f"/api/v1/documents/jobs/{job_id}")
        assert r.status_code == 200
        last_body = r.json()
        status = last_body["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.1)

    assert status == "failed", last_body
    assert last_body.get("error_message")


def test_document_job_long_poll_wait(api_client, tmp_path: Path) -> None:
    """wait=true holds one request until the job reaches a terminal status."""
    client, _, _ = api_client
    docx_bytes = _sample_docx_bytes(tmp_path)
    data = _sample_json()

    resp = client.post(
        "/api/v1/documents/jobs",
        files={"template": ("template.docx", docx_bytes, "application/octet-stream")},
        data={"data": json.dumps(data), "skip_validation": "true"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    r = client.get(
        f"/api/v1/documents/jobs/{job_id}",
        params={"wait": "true", "timeout": 30},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body.get("error_message")


def test_job_store_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "custom_storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "custom.db"))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "local")
    monkeypatch.delenv("AZURE_SQL_SERVER", raising=False)
    monkeypatch.delenv("AZURE_SQL_PASSWORD", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

    from ip_api.core.settings import reload_settings

    reload_settings()
    cfg = get_settings()
    assert cfg.storage_base_path == (tmp_path / "custom_storage").resolve()

    store = JobStore()
    jid, job_dir, _tpl, _data, _out = store.create_job_paths()
    assert job_dir == cfg.job_dir(jid)
    reload_settings()


def test_transcribe_requires_audio(api_client) -> None:
    client, _, _ = api_client
    resp = client.post("/api/v1/audio/transcribe")
    assert resp.status_code == 422


def test_voice_contract_saved_to_sqlite(api_client) -> None:
    client, _, db_path = api_client
    # Step 1: LangGraph start → interrupt (needs_confirmation + thread_id)
    resp = client.post(
        "/api/v1/voice/contract",
        json={
            "transcript": (
                "please create contract with legal entity AVC "
                "contract reference number CR 1001"
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_confirmation"
    assert body["thread_id"]
    assert body["contract_reference_number"] == "CR-1001"
    assert body["legal_entity"]["code"] == "AVC"

    # Step 2: resume LangGraph HITL → create + save
    confirm = client.post(
        "/api/v1/voice/contract/confirm",
        json={
            "legal_entity": "AVC",
            "contract_reference_number": "CR-1001",
            "transcript": body["transcript"],
            "thread_id": body["thread_id"],
            "user_text": "yes",
        },
    )
    assert confirm.status_code == 200
    created = confirm.json()
    assert created["ok"] is True
    assert created["contract_id"]
    assert created["contract_text"]
    assert "Saved to SQLite" in created["message"]
    assert db_path.exists()

    get_resp = client.get(f"/api/v1/voice/contracts/{created['contract_id']}")
    assert get_resp.status_code == 200
    saved = get_resp.json()
    assert saved["spoken_number"] == "CR-1001"

    txt = client.get(
        f"/api/v1/voice/contracts/{created['contract_id']}/download",
        params={"format": "txt"},
    )
    assert txt.status_code == 200
    assert b"SUPPLY CONTRACT" in txt.content


def test_voice_contract_irrelevant_not_saved(api_client) -> None:
    client, _, _ = api_client
    resp = client.post(
        "/api/v1/voice/contract",
        json={"transcript": "Play some music please"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body.get("contract_id") is None
    assert body["message"] == "Please ask a relevant service."

    listed = client.get("/api/v1/voice/contracts").json()
    assert listed["count"] == 0


def test_document_job_status_includes_elapsed(api_client, tmp_path: Path) -> None:
    client, _, _ = api_client
    store = JobStore()
    job_id, _job_dir, tpl, data, out = store.create_job_paths()
    tpl.write_bytes(b"docx")
    data.write_text("{}", encoding="utf-8")
    store.insert_job(job_id, tpl, data, out)
    store.complete_job(
        job_id,
        result={
            "status": "completed",
            "elapsed_ms": 12345.6,
            "elapsed": "12.3 s",
        },
    )

    resp = client.get(f"/api/v1/documents/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["elapsed"] == "12.3 s"
    assert body["elapsed_ms"] == 12345.6

    listed = client.get("/api/v1/documents/jobs").json()
    match = next(j for j in listed["jobs"] if j["job_id"] == job_id)
    assert match["elapsed"] == "12.3 s"


def test_document_job_elapsed_from_ms_only(api_client) -> None:
    """elapsed_ms without an elapsed string still produces a human duration."""
    client, _, _ = api_client
    store = JobStore()
    job_id, _job_dir, tpl, data, out = store.create_job_paths()
    tpl.write_bytes(b"docx")
    data.write_text("{}", encoding="utf-8")
    store.insert_job(job_id, tpl, data, out)
    store.complete_job(job_id, result={"status": "completed", "elapsed_ms": "45200"})

    body = client.get(f"/api/v1/documents/jobs/{job_id}").json()
    assert body["elapsed"] == "45.2 s"
    assert body["elapsed_ms"] == 45200.0


def test_document_job_elapsed_falls_back_to_timestamps(api_client) -> None:
    client, _, _ = api_client
    store = JobStore()
    job_id, _job_dir, tpl, data, out = store.create_job_paths()
    tpl.write_bytes(b"docx")
    data.write_text("{}", encoding="utf-8")
    store.insert_job(job_id, tpl, data, out)
    time.sleep(0.05)
    store.complete_job(job_id)

    resp = client.get(f"/api/v1/documents/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["elapsed"]
    assert body["elapsed_ms"] is not None
    assert body["elapsed_ms"] >= 0
