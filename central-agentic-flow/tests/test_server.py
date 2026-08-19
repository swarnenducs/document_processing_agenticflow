"""MAF HTTP app smoke tests (no live LLM)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from central_agentic_flow.server import create_app


def test_health_route_exists() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/health" in paths or "/ask/health" in paths


def test_health_ok() -> None:
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
