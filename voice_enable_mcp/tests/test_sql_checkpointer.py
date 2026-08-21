"""Voice HITL checkpoints persist in SQLite / Azure SQL, not MemorySaver."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, select

from voice_enable_mcp.graph import reset_voice_graph
from voice_enable_mcp.services.voice_contract_workflow import (
    confirm_voice_contract,
    run_voice_contract_workflow,
)
from voice_enable_mcp.storage.db import get_engine
from voice_enable_mcp.storage.job_store import JobStore
from voice_enable_mcp.storage.models import LgCheckpoint


def test_checkpoint_tables_are_created_on_sqlite() -> None:
    JobStore()
    tables = set(inspect(get_engine()).get_table_names())
    assert "lg_checkpoints" in tables
    assert "lg_checkpoint_blobs" in tables
    assert "lg_checkpoint_writes" in tables


def test_hitl_interrupt_writes_checkpoint_rows() -> None:
    store = JobStore()
    pending = run_voice_contract_workflow(
        "please create contract with legal entity AVC contract reference number CR 1001",
        store=store,
    )
    assert pending.status == "needs_confirmation"
    assert pending.thread_id

    with get_engine().connect() as conn:
        rows = conn.execute(
            select(LgCheckpoint.thread_id).where(LgCheckpoint.thread_id == pending.thread_id)
        ).all()
    assert rows, "interrupt() must persist a LangGraph checkpoint in SQL"


def test_hitl_resume_survives_compiled_graph_reset(tmp_path: Path) -> None:
    """Same SQLite file, new compiled graph — stands in for a process restart."""
    store = JobStore()
    pending = run_voice_contract_workflow(
        "please create contract with legal entity AVC contract reference number CR 1001",
        store=store,
        output_dir=tmp_path / "out",
    )
    assert pending.status == "needs_confirmation"
    thread_id = pending.thread_id
    assert thread_id

    reset_voice_graph()

    result = confirm_voice_contract(
        entity_code_or_name="AVC",
        contract_reference_number="CR-1001",
        store=store,
        thread_id=thread_id,
        user_text="yes",
        output_dir=tmp_path / "out",
    )
    assert result.ok is True
    assert result.status == "completed"
    assert result.contract_text
    assert "SUPPLY CONTRACT" in result.contract_text
