"""Tests for voice → legal entity + HITL pricelist → dummy contract (LangGraph)."""

from __future__ import annotations

from pathlib import Path

from document_processing_agenticflow.services.voice_contract_workflow import (
    confirm_voice_contract,
    extract_legal_entity_and_reference,
    normalize_contract_ref,
    run_voice_contract_workflow,
)
from document_processing_agenticflow.storage.job_store import JobStore


def test_extract_flexible_prompt_without_with_and_spaced_ref() -> None:
    entity, ref = extract_legal_entity_and_reference(
        "please create contract with legal entity AVC contract reference number CR 1001"
    )
    assert entity == "AVC"
    assert normalize_contract_ref(ref) == "CR1001"


def test_irrelevant_instruction_returns_ask_relevant_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    result = run_voice_contract_workflow("What is the weather today?", store=JobStore())
    assert result.ok is False
    assert result.status == "rejected"
    assert result.message == "Please ask a relevant service."
    settings_mod._settings = None


def test_create_contract_needs_human_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    store = JobStore()
    result = run_voice_contract_workflow(
        "please create contract with legal entity AVC contract reference number CR 1001",
        store=store,
    )
    assert result.ok is False
    assert result.status == "needs_confirmation"
    assert result.thread_id  # LangGraph HITL thread
    assert result.legal_entity["code"] == "AVC"
    assert result.contract_reference_number == "CR-1001"
    assert result.candidates
    settings_mod._settings = None


def test_langgraph_interrupt_resume_creates_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    store = JobStore()
    pending = run_voice_contract_workflow(
        "please create contract with legal entity AVC contract reference number CR 1001",
        store=store,
        output_dir=tmp_path / "out",
    )
    assert pending.status == "needs_confirmation"
    assert pending.thread_id

    result = confirm_voice_contract(
        entity_code_or_name="AVC",
        contract_reference_number="CR-1001",
        store=store,
        thread_id=pending.thread_id,
        user_text="yes",
        output_dir=tmp_path / "out",
    )
    assert result.ok is True
    assert result.status == "completed"
    assert result.contract_text
    assert "SUPPLY CONTRACT" in result.contract_text
    assert Path(result.contract_text_file).is_file()
    assert Path(result.contract_file).is_file()
    settings_mod._settings = None


def test_confirm_creates_text_and_docx(tmp_path: Path, monkeypatch) -> None:
    """Compatibility path without thread_id (direct finalize)."""
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    store = JobStore()
    result = confirm_voice_contract(
        entity_code_or_name="AVC",
        contract_reference_number="CR 1001",
        store=store,
        output_dir=tmp_path / "out",
    )
    assert result.ok is True
    assert result.status == "completed"
    assert result.contract_text
    assert "SUPPLY CONTRACT" in result.contract_text
    assert Path(result.contract_text_file).is_file()
    assert Path(result.contract_file).is_file()
    settings_mod._settings = None


def test_unknown_entity_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    import document_processing_agenticflow.core.settings as settings_mod

    settings_mod._settings = None
    result = run_voice_contract_workflow(
        "Please create contract with Legal entity UNKNOWN with contract reference number CR-1001",
        store=JobStore(),
    )
    assert result.ok is False
    assert "No legal entity found" in result.message
    settings_mod._settings = None
