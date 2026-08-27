"""OpenAPI / Swagger metadata is present and tagged."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ip_api.api.main import create_app, cors_allow_origins


def test_openapi_has_operator_overview() -> None:
    spec = create_app().openapi()
    assert spec["info"]["title"] == "ipp_agentic_api"
    desc = spec["info"]["description"]
    assert "ipp_agentic_api" in desc
    assert "POST" in desc and "/api/v1/documents/jobs" in desc
    assert "X-Admin-Api-Key" in desc
    tag_names = {t["name"] for t in spec["tags"]}
    assert {"health", "documents", "voice", "admin", "maf", "mcp-agents"} <= tag_names


def test_openapi_paths_have_summaries() -> None:
    spec = create_app().openapi()
    jobs = spec["paths"]["/api/v1/documents/jobs"]["post"]
    assert jobs.get("summary")
    assert "multipart" in (jobs.get("description") or "").lower()
    assert "wait=true" in (jobs.get("description") or "")
    voice = spec["paths"]["/api/v1/voice/contract"]["post"]
    assert voice.get("summary")
    assert "thread_id" in (voice.get("description") or "")
    health = spec["paths"]["/api/v1/health"]["get"]
    assert health.get("tags") == ["health"]


def test_cors_defaults_include_angular() -> None:
    origins = cors_allow_origins()
    assert "http://localhost:4200" in origins


def test_cors_preflight_from_angular() -> None:
    client = TestClient(create_app())
    resp = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code in {200, 204}
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:4200"
