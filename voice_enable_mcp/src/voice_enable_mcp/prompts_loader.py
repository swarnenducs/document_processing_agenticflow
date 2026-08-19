"""Load ChatPromptTemplate content from YAML (voice_enable_mcp/prompts)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from langchain_core.prompts import ChatPromptTemplate


def _component_root() -> Path:
    return Path(__file__).resolve().parents[2]


_PACKAGE_DEFAULTS = Path(__file__).resolve().parent / "services" / "prompts" / "yml"


def prompts_dir() -> Path:
    override = (os.getenv("VOICE_PROMPTS_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_component_root() / "prompts").resolve()


def resolve_prompt_path(filename: str) -> Path:
    """
    Resolution order:
      1) VOICE_PROMPTS_DIR / <filename>
      2) voice_enable_mcp/prompts/<filename>
      3) packaged defaults under services/prompts/yml/<filename>
      4) PROMPTS_DIR / <filename> (legacy root)
    """
    candidates = [
        prompts_dir() / filename,
        _PACKAGE_DEFAULTS / filename,
    ]
    legacy = (os.getenv("PROMPTS_DIR") or "").strip()
    if legacy:
        candidates.append(Path(legacy).expanduser().resolve() / filename)
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Voice prompt '{filename}' not found in {prompts_dir()} "
        f"or package defaults {_PACKAGE_DEFAULTS}. "
        "Set VOICE_PROMPTS_DIR or add the YAML file."
    )


def load_prompt_yaml(filename: str, *, reload: bool = True) -> dict[str, Any]:
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
