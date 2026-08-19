"""UI settings: API URL and Gradio bind address only (no pipeline / storage logic)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# core/ → package → src → <component folder>
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")
_monorepo = _PROJECT_ROOT.parent
if (_monorepo / "run_all_components.py").is_file():
    load_dotenv(_monorepo / ".env", override=False)
load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    gradio_host: str
    gradio_port: int


def get_settings() -> Settings:
    return Settings(
        api_base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        gradio_host=os.getenv("GRADIO_HOST", "127.0.0.1"),
        gradio_port=int(os.getenv("GRADIO_PORT", "7860")),
    )


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return settings()
