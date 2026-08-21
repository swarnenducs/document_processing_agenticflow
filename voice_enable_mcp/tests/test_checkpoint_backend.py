"""SQL (default) vs Redis LangGraph checkpointer swap."""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_enable_mcp.core.settings import reload_settings
from voice_enable_mcp.graph import build_voice_contract_graph, reset_voice_graph
from voice_enable_mcp.services.voice_contract_workflow import (
    confirm_voice_contract,
    run_voice_contract_workflow,
)
from voice_enable_mcp.storage.checkpointer import get_checkpointer
from voice_enable_mcp.storage.checkpoint_store import SqlAlchemyCheckpointSaver
from voice_enable_mcp.storage.job_store import JobStore
from voice_enable_mcp.storage.redis_checkpoint_store import RedisCheckpointSaver


def test_default_checkpointer_is_sql() -> None:
    saver = get_checkpointer()
    assert isinstance(saver, SqlAlchemyCheckpointSaver)


def test_unknown_backend_raises(monkeypatch) -> None:
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_BACKEND", "postgres")
    reload_settings()
    with pytest.raises(ValueError, match="sql' or 'redis"):
        get_checkpointer()


def test_redis_backend_selects_redis_saver(monkeypatch) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_BACKEND", "redis")
    reload_settings()
    saver = get_checkpointer(redis_client=fakeredis.FakeRedis(decode_responses=True))
    assert isinstance(saver, RedisCheckpointSaver)


def test_redis_hitl_survives_compiled_graph_reset(tmp_path: Path, monkeypatch) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_BACKEND", "redis")
    reload_settings()
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisCheckpointSaver(client=client)

    import voice_enable_mcp.graph as graph_mod

    reset_voice_graph()
    graph_mod._GRAPH = build_voice_contract_graph(checkpointer=saver)

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
    graph_mod._GRAPH = build_voice_contract_graph(checkpointer=saver)

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
