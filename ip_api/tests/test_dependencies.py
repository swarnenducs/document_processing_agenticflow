"""ApplicationContext is built in lifespan and injected via FastAPI Depends."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ip_api.api.dependencies import get_app_context
from ip_api.api.main import create_app
from ip_api.storage.job_store import JobStore
from ip_api.storage.template_store import TemplateStore


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    storage = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_BASE_PATH", str(storage))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "local")
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

    reload_settings()
    with TestClient(create_app()) as client:
        yield client
    reload_settings()


def test_lifespan_builds_shared_stores(api_client) -> None:
    ctx = get_app_context()
    assert isinstance(ctx.job_store, JobStore)
    assert isinstance(ctx.template_store, TemplateStore)
    health = api_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] in {"ok", "degraded"}
