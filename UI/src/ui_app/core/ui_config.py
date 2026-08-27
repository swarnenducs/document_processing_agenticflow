"""Runtime UI JSON: which ipp_agentic_api host to call (local vs Azure).

Committed example: ``UI/config/ui_targets.example.json``.
Local overlay (gitignored): ``UI/config/ui_runtime.json``.
The Gradio **API targets** tab can edit and apply this JSON without restarting.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

_UI_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_PATH = _UI_ROOT / "config" / "ui_targets.example.json"
RUNTIME_PATH = _UI_ROOT / "config" / "ui_runtime.json"

_DEFAULT: dict[str, Any] = {
    "active_target": "local",
    "admin_api_key": "",
    "targets": {
        "local": {
            "label": "Local ipp_agentic_api",
            "api_base_url": "http://127.0.0.1:8000",
        },
        "azure": {
            "label": "Azure Web App (replace hostname)",
            "api_base_url": "https://<api-app>.azurewebsites.net",
        },
    },
}

_state: dict[str, Any] | None = None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in overlay.items():
        if key == "targets" and isinstance(value, dict) and isinstance(out.get("targets"), dict):
            merged = dict(out["targets"])
            for name, spec in value.items():
                if isinstance(spec, dict) and isinstance(merged.get(name), dict):
                    merged[name] = {**merged[name], **spec}
                else:
                    merged[name] = spec
            out["targets"] = merged
        else:
            out[key] = value
    return out


def load_ui_config() -> dict[str, Any]:
    global _state
    from ui_app.core.settings import settings

    merged = deepcopy(_DEFAULT)
    merged = _merge(merged, _read_json(EXAMPLE_PATH))
    merged = _merge(merged, _read_json(RUNTIME_PATH))
    env_url = (settings().api_base_url or "").strip()
    targets = merged.setdefault("targets", {})
    if env_url and isinstance(targets.get("local"), dict) and not _read_json(RUNTIME_PATH):
        targets["local"]["api_base_url"] = env_url
    _state = merged
    return deepcopy(_state)


def current_config() -> dict[str, Any]:
    if _state is None:
        return load_ui_config()
    return deepcopy(_state)


def dumps_config() -> str:
    return json.dumps(current_config(), indent=2) + "\n"


def get_api_base_url() -> str:
    cfg = current_config()
    name = str(cfg.get("active_target") or "local").strip() or "local"
    targets = cfg.get("targets") if isinstance(cfg.get("targets"), dict) else {}
    spec = targets.get(name) if isinstance(targets.get(name), dict) else {}
    url = str(spec.get("api_base_url") or "").strip()
    if url:
        return url.rstrip("/")
    from ui_app.core.settings import settings

    return settings().api_base_url.rstrip("/")


def get_admin_api_key() -> str:
    from_json = str(current_config().get("admin_api_key") or "").strip()
    if from_json:
        return from_json
    return str(os.environ.get("ADMIN_API_KEY") or "").strip()


def apply_ui_config(raw_json: str) -> dict[str, Any]:
    """Parse JSON from the UI, persist runtime file, and use it for HTTP calls."""
    global _state
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        raise ValueError("UI config JSON root must be an object")
    targets = data.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise ValueError("UI config needs a non-empty 'targets' object")
    active = str(data.get("active_target") or "").strip()
    if not active or active not in targets:
        raise ValueError("active_target must be a key in targets")
    spec = targets[active]
    if not isinstance(spec, dict) or not str(spec.get("api_base_url") or "").strip():
        raise ValueError(f"targets.{active}.api_base_url is required")
    _state = _merge(_DEFAULT, data)
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps(_state, indent=2) + "\n", encoding="utf-8")
    return deepcopy(_state)
