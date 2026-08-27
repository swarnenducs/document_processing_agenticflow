"""MAF prompts are selected by config/prompt_versions.json."""

from pathlib import Path

import pytest

from central_agentic_flow.prompt_catalog import (
    catalog_prompt_files,
    load_named_prompt,
    load_validator_prompt,
    prompt_versions_path,
)
from central_agentic_flow.prompt_versions import load_prompt_versions


def test_versions_json_selects_validator() -> None:
    catalog = load_prompt_versions(prompt_versions_path())
    assert catalog["persona_prompt_validator"].required_version == "1.0.0"
    spec = load_validator_prompt()
    assert spec.version == "1.0.0"
    assert "Persona Prompt Validator" in spec.body
    assert not spec.body.startswith("---")


def test_catalog_lists_required_versions() -> None:
    names = {item["name"] for item in catalog_prompt_files()}
    assert names == {
        "orchestrator_instructions",
        "persona_prompt_validator",
        "role_access",
    }
    for item in catalog_prompt_files():
        assert item["required_version"] == "1.0.0"
        assert Path(item["path"]).is_file()


def test_repo_root_prompts_pointer_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = tmp_path / "prompts"
    pointer.mkdir()
    (pointer / "README.md").write_text("pointer only\n", encoding="utf-8")
    monkeypatch.delenv("MAF_PROMPTS_DIR", raising=False)
    monkeypatch.setenv("PROMPTS_DIR", str(pointer))
    spec = load_validator_prompt()
    assert spec.version == "1.0.0"
    assert "guardrails" in str(spec.path)


def test_missing_required_version_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "prompt_versions.json").write_text(
        '{"prompts": {"persona_prompt_validator": {"required_version": "9.9.9",'
        '"path": "guardrails/persona_prompt_validator.{version}.md"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MAF_PROMPTS_DIR", str(tmp_path / "prompts"))
    monkeypatch.setenv("MAF_PROMPT_VERSIONS_FILE", str(tmp_path / "config" / "prompt_versions.json"))
    with pytest.raises(FileNotFoundError, match="9.9.9"):
        load_named_prompt("persona_prompt_validator")
