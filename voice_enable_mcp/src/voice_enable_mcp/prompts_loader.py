"""Voice MCP prompt helpers (YAML under voice_enable_mcp/prompts/)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _component_root() -> Path:
    return Path(__file__).resolve().parents[4]


def prompts_dir() -> Path:
    override = (
        os.getenv("VOICE_PROMPTS_DIR", "").strip()
        or os.getenv("PROMPTS_DIR", "").strip()
    )
    if override:
        return Path(override).expanduser().resolve()
    return (_component_root() / "prompts").resolve()


def load_prompt_yaml(filename: str) -> dict[str, Any]:
    path = prompts_dir() / filename
    if not path.is_file():
        raise FileNotFoundError(f"Voice prompt not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Prompt YAML root must be a mapping: {path}")
    return data
