"""Admin PyJWT mint + verify."""

from __future__ import annotations

from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from ip_api.api.main import create_app
from ip_api.services.admin_jwt import AUDIENCE, ISSUER
from test_admin_templates import ADMIN_KEY, HEADERS, _isolate_local


def test_get_token_alias_and_ttl(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch, admin_key=None)
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/admin/token", params={"ttl_seconds": 120})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["expires_in"] == 120
        claims = jwt.decode(
            body["access_token"],
            options={"verify_signature": False},
        )
        assert claims["iss"] == ISSUER
        assert claims["aud"] == AUDIENCE
        assert claims["sub"] == "admin"
        assert claims["typ"] == "admin_access"
        assert claims["exp"] - claims["iat"] == 120

    from ip_api.core.settings import reload_settings

    reload_settings()


def test_forged_jwt_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch, admin_key=ADMIN_KEY)
    forged = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "admin", "typ": "admin_access"},
        "wrong-secret",
        algorithm="HS256",
    )
    with TestClient(create_app()) as client:
        resp = client.get(
            "/api/v1/admin/templates",
            headers={"Authorization": f"Bearer {forged}"},
        )
        assert resp.status_code == 401

    from ip_api.core.settings import reload_settings

    reload_settings()


def test_static_key_still_works_without_jwt(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch, admin_key=ADMIN_KEY)
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/admin/templates", headers=HEADERS)
        assert resp.status_code == 200

    from ip_api.core.settings import reload_settings

    reload_settings()
