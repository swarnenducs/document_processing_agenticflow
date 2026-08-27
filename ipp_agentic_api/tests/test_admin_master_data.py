"""Admin API for legal/sales master_data SQL rows."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ip_api.api.main import create_app
from test_admin_templates import HEADERS, _isolate_local

LEGAL = {
    "placeholder_key": "Legal_Department_Master_Data",
    "category": "legal",
    "content": (
        "Legal Department\n"
        "200 Connell Drive, Suite 1000\n"
        "Berkeley Heights, NJ 07922\n"
        "E-mail: pmo@ABCTec.com"
    ),
    "active": True,
}

SALES = {
    "placeholder_key": "Sales_Excellence_Master_Data",
    "category": "sales",
    "content": (
        "Sales Excellence\n"
        "200 Connell Drive, Suite 1000\n"
        "Berkeley Heights, NJ 07922\n"
        "E-mail: pmo@ABCTec.com"
    ),
    "active": True,
}


def test_post_adds_master_data_rows(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        created = client.post("/api/v1/admin/master-data", headers=HEADERS, json=LEGAL)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["placeholder_key"] == LEGAL["placeholder_key"]
        assert "Legal Department" in body["content"]

        again = client.post("/api/v1/admin/master-data", headers=HEADERS, json=SALES)
        assert again.status_code == 201

        listing = client.get("/api/v1/admin/master-data", headers=HEADERS)
        assert listing.status_code == 200
        keys = {item["placeholder_key"] for item in listing.json()["items"]}
        assert LEGAL["placeholder_key"] in keys
        assert SALES["placeholder_key"] in keys


def test_put_updates_content(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        client.post("/api/v1/admin/master-data", headers=HEADERS, json=LEGAL)
        updated = client.put(
            f"/api/v1/admin/master-data/{LEGAL['placeholder_key']}",
            headers=HEADERS,
            json={"content": "Legal Department\nSuite 200", "active": True},
        )
        assert updated.status_code == 200
        assert updated.json()["content"] == "Legal Department\nSuite 200"


def test_get_and_delete_master_data(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        client.post("/api/v1/admin/master-data", headers=HEADERS, json=SALES)
        got = client.get(
            f"/api/v1/admin/master-data/{SALES['placeholder_key']}",
            headers=HEADERS,
        )
        assert got.status_code == 200
        deleted = client.delete(
            f"/api/v1/admin/master-data/{SALES['placeholder_key']}",
            headers=HEADERS,
        )
        assert deleted.status_code == 200
        missing = client.get(
            f"/api/v1/admin/master-data/{SALES['placeholder_key']}",
            headers=HEADERS,
        )
        assert missing.status_code == 404


def test_master_data_requires_admin_key(tmp_path: Path, monkeypatch) -> None:
    _isolate_local(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/admin/master-data").status_code == 401
        assert (
            client.post(
                "/api/v1/admin/master-data",
                json=LEGAL,
            ).status_code
            == 401
        )
