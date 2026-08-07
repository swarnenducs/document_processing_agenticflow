"""Tests for in-process job progress hub + WebSocket stages."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from document_processing_agenticflow.api.main import create_app
from document_processing_agenticflow.services.job_events import JobEventHub
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


def test_job_event_hub_history_and_terminal() -> None:
    hub = JobEventHub(history_limit=10)
    hub.publish("j1", "accepted")
    hub.publish("j1", "styles_extracted")
    hub.publish("j1", "completed")

    async def _collect():
        out = []
        async for event in hub.subscribe("j1"):
            out.append(event["stage"])
        return out

    stages = asyncio.run(_collect())
    assert stages == ["accepted", "styles_extracted", "completed"]


def test_document_job_ws_url_in_accept(api_client, tmp_path: Path) -> None:
    client, _, _ = api_client
    docx = build_sample_template(tmp_path / "t.docx").read_bytes()
    resp = client.post(
        "/api/v1/documents/jobs",
        files={"template": ("template.docx", docx, "application/octet-stream")},
        data={
            "data": json.dumps({"invoice_number": "WS-1"}),
            "skip_validation": "true",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["ws_url"] == f"/api/v1/documents/jobs/{body['job_id']}/ws"


def test_document_job_websocket_receives_terminal(api_client, tmp_path: Path) -> None:
    client, _, _ = api_client
    docx = build_sample_template(tmp_path / "t.docx").read_bytes()
    resp = client.post(
        "/api/v1/documents/jobs",
        files={"template": ("template.docx", docx, "application/octet-stream")},
        data={
            "data": json.dumps({"invoice_number": "WS-2"}),
            "skip_validation": "true",
        },
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    with client.websocket_connect(f"/api/v1/documents/jobs/{job_id}/ws") as ws:
        stages: list[str] = []
        deadline = time.time() + 30
        while time.time() < deadline:
            msg = ws.receive_json()
            stages.append(str(msg.get("stage")))
            if msg.get("terminal") or msg.get("stage") in {"completed", "failed"}:
                break
        assert stages
        assert stages[-1] in {"failed", "completed"}
