"""UI JSON config selects which API host Gradio calls."""

from __future__ import annotations

import json
from pathlib import Path

from ui_app.core import ui_config


def test_apply_ui_config_switches_api_host(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "ui_runtime.json"
    monkeypatch.setattr(ui_config, "RUNTIME_PATH", runtime)
    monkeypatch.setattr(ui_config, "EXAMPLE_PATH", tmp_path / "missing.json")
    ui_config._state = None
    payload = {
        "active_target": "azure",
        "admin_api_key": "secret-admin",
        "targets": {
            "local": {"label": "local", "api_base_url": "http://127.0.0.1:8000"},
            "azure": {
                "label": "azure",
                "api_base_url": "https://example.azurewebsites.net",
            },
        },
    }
    ui_config.apply_ui_config(json.dumps(payload))
    assert ui_config.get_api_base_url() == "https://example.azurewebsites.net"
    assert ui_config.get_admin_api_key() == "secret-admin"
    saved = json.loads(runtime.read_text(encoding="utf-8"))
    assert saved["active_target"] == "azure"


def test_admin_api_key_falls_back_to_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ui_config, "RUNTIME_PATH", tmp_path / "ui_runtime.json")
    monkeypatch.setattr(ui_config, "EXAMPLE_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("ADMIN_API_KEY", "from-env")
    ui_config._state = None
    ui_config.load_ui_config()
    assert ui_config.get_admin_api_key() == "from-env"
