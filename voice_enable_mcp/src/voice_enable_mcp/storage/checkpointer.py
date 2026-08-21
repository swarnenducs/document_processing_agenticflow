"""Pick the LangGraph HITL checkpointer: SQLAlchemy (default) or Redis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from voice_enable_mcp.core.settings import settings
from voice_enable_mcp.storage.checkpoint_store import SqlAlchemyCheckpointSaver

_SQL_ALIASES = {"sql", "sqlite", "mssql", "azure_sql", "azure-sql", ""}
_REDIS_ALIASES = {"redis", "rediss"}


def get_checkpointer(
    *,
    sqlite_path: Path | None = None,
    redis_client: Any | None = None,
) -> BaseCheckpointSaver:
    """Return the configured HITL checkpointer.

    ``LANGGRAPH_CHECKPOINT_BACKEND``:
    - ``sql`` (default) — SQLite locally, Azure SQL in cloud
    - ``redis`` — ``REDIS_URL`` (vanilla Redis / Azure Cache)
    """
    backend = (settings().checkpoint_backend or "sql").strip().lower()
    if backend in _REDIS_ALIASES:
        from voice_enable_mcp.storage.redis_checkpoint_store import RedisCheckpointSaver

        if redis_client is not None:
            return RedisCheckpointSaver(
                client=redis_client,
                prefix=settings().checkpoint_redis_prefix,
                ttl_seconds=settings().checkpoint_redis_ttl_seconds,
            )
        url = (settings().redis_url or "").strip() or "redis://127.0.0.1:6379/0"
        return RedisCheckpointSaver.from_url(
            url,
            prefix=settings().checkpoint_redis_prefix,
            ttl_seconds=settings().checkpoint_redis_ttl_seconds,
        )
    if backend in _SQL_ALIASES:
        return SqlAlchemyCheckpointSaver(sqlite_path=sqlite_path)
    raise ValueError(
        f"Unknown LANGGRAPH_CHECKPOINT_BACKEND={backend!r}. Use 'sql' or 'redis'."
    )
