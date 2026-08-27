"""MAF prompt file locations: JSON required version → versioned markdown file."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from central_agentic_flow.prompt_versions import (
    assert_file_version,
    catalog_as_dicts,
    load_prompt_versions,
    resolve_versioned_path,
    versions_file,
)

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
_COMPONENT_ROOT = Path(__file__).resolve().parents[2]
_COMPONENT_PROMPTS = (_COMPONENT_ROOT / "prompts").resolve()


@dataclass(frozen=True)
class MarkdownPrompt:
    name: str
    version: str
    body: str
    path: Path
    meta: dict[str, Any]


def _looks_like_maf_prompts(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    if (folder / "guardrails").is_dir():
        return True
    return any(folder.glob("**/persona_prompt_validator*.md"))


def _resolve_prompts_override(raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    component_rel = (_COMPONENT_ROOT / path).resolve()
    cwd_rel = (Path.cwd() / path).resolve()
    if _looks_like_maf_prompts(component_rel):
        return component_rel
    if _looks_like_maf_prompts(cwd_rel):
        return cwd_rel
    return component_rel


def prompts_dir() -> Path:
    """Prefer ``central-agentic-flow/prompts``, not the repo-root ``./prompts`` pointer.

    ``PROMPTS_DIR=./prompts`` from the monorepo cwd is only a README folder.
    ``MAF_PROMPTS_DIR=./prompts`` is resolved against the MAF package, not cwd.
    """
    maf = (os.getenv("MAF_PROMPTS_DIR") or "").strip()
    if maf:
        resolved = _resolve_prompts_override(maf)
        if _looks_like_maf_prompts(resolved):
            return resolved
        if _looks_like_maf_prompts(_COMPONENT_PROMPTS):
            return _COMPONENT_PROMPTS
        return resolved
    legacy = (os.getenv("PROMPTS_DIR") or "").strip()
    if legacy:
        resolved = _resolve_prompts_override(legacy)
        if _looks_like_maf_prompts(resolved):
            return resolved
    return _COMPONENT_PROMPTS


def guardrails_dir() -> Path:
    return (prompts_dir() / "guardrails").resolve()


def prompt_versions_path() -> Path:
    return versions_file(
        env_names=("MAF_PROMPT_VERSIONS_FILE", "PROMPT_VERSIONS_FILE"),
        default=_COMPONENT_ROOT / "config" / "prompt_versions.json",
    )


def prompt_version_catalog():
    return load_prompt_versions(prompt_versions_path())


def parse_markdown_prompt(text: str, *, path: Path) -> MarkdownPrompt:
    raw = text.strip()
    meta: dict[str, Any] = {}
    body = raw
    match = _FRONTMATTER.match(raw)
    if match:
        loaded = yaml.safe_load(match.group(1)) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Prompt frontmatter must be a mapping: {path}")
        meta = {str(key): value for key, value in loaded.items()}
        body = raw[match.end() :].strip()
    version = str(meta.get("version") or "").strip()
    if not version:
        raise ValueError(f"Prompt file missing frontmatter version: {path}")
    name = str(meta.get("name") or path.stem).strip() or path.stem
    body = _strip_md_heading(body)
    if not body:
        raise ValueError(f"Prompt file has empty body: {path}")
    return MarkdownPrompt(name=name, version=version, body=body, path=path, meta=meta)


def load_markdown_prompt(path: Path, *, required_version: str | None = None) -> MarkdownPrompt:
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt file: {path}")
    spec = parse_markdown_prompt(path.read_text(encoding="utf-8"), path=path)
    if required_version is not None:
        assert_file_version(spec.version, required_version, path=path)
    return spec


def _strip_md_heading(text: str) -> str:
    stripped = text.strip()
    lines = stripped.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        stripped = "\n".join(lines[1:]).strip()
    return stripped


def load_named_prompt(name: str) -> MarkdownPrompt:
    catalog = prompt_version_catalog()
    path, required = resolve_versioned_path(
        name=name,
        prompts_dir=prompts_dir(),
        catalog=catalog,
    )
    return load_markdown_prompt(path, required_version=required)


def load_guardrail_prompt() -> MarkdownPrompt:
    return load_named_prompt("role_access")


def load_guardrail_instructions() -> str:
    try:
        return load_guardrail_prompt().body
    except FileNotFoundError:
        return ""


def load_validator_prompt() -> MarkdownPrompt:
    return load_named_prompt("persona_prompt_validator")


def load_orchestrator_prompt() -> MarkdownPrompt | None:
    try:
        return load_named_prompt("orchestrator_instructions")
    except FileNotFoundError:
        return None


def catalog_prompt_files() -> list[dict[str, Any]]:
    return catalog_as_dicts(prompt_version_catalog(), prompts_dir=prompts_dir())
