"""Load ChatPromptTemplate content from YAML files (editable without code deploy)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from langchain_core.prompts import ChatPromptTemplate

# project root: .../document_processing_agenticflow/
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PACKAGE_DEFAULTS = Path(__file__).resolve().parent / "yml"


def prompts_dir() -> Path:
    """Directory containing mapper.yml / validator.yml."""
    override = os.getenv("PROMPTS_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_PROJECT_ROOT / "prompts").resolve()


def resolve_prompt_path(filename: str) -> Path:
    """
    Resolution order:
      1) PROMPTS_DIR/<filename> (or ./prompts/<filename>)
      2) packaged defaults under services/prompts/yml/<filename>
    """
    primary = prompts_dir() / filename
    if primary.is_file():
        return primary
    fallback = _PACKAGE_DEFAULTS / filename
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        f"Prompt file '{filename}' not found in {prompts_dir()} "
        f"or package defaults {_PACKAGE_DEFAULTS}. "
        "Set PROMPTS_DIR or add the YAML file."
    )


def load_prompt_yaml(filename: str, *, reload: bool = True) -> dict[str, Any]:
    """Load a prompt YAML. Reloads from disk each call so edits apply without restart."""
    path = resolve_prompt_path(filename)
    if reload:
        _load_yaml_cached.cache_clear()
    return _load_yaml_cached(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def _load_yaml_cached(path_str: str, _mtime_ns: int) -> dict[str, Any]:
    path = Path(path_str)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Prompt YAML root must be a mapping: {path}")
    system = data.get("system")
    human = data.get("human")
    if not isinstance(system, str) or not system.strip():
        raise ValueError(f"Prompt YAML missing non-empty 'system' string: {path}")
    if not isinstance(human, str) or not human.strip():
        raise ValueError(f"Prompt YAML missing non-empty 'human' string: {path}")
    return {
        "name": str(data.get("name") or path.stem),
        "system": system.strip(),
        "human": human.strip(),
        "path": str(path),
    }


def chat_prompt_from_yaml(filename: str) -> ChatPromptTemplate:
    payload = load_prompt_yaml(filename)
    return ChatPromptTemplate.from_messages(
        [
            ("system", payload["system"]),
            ("human", payload["human"]),
        ]
    )
