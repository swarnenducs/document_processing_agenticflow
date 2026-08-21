"""LangGraph checkpointer backed by the same SQLAlchemy engine as voice MCP.

Local runs persist HITL state in SQLite; Azure SQL is used when
``AZURE_SQL_*`` / ``SQLALCHEMY_DATABASE_URL`` is set. Survives process
restarts and is shared across workers that hit the same database.

This is the default durable stand-in for ``MemorySaver``. Set
``LANGGRAPH_CHECKPOINT_BACKEND=redis`` to use Redis instead (see
``redis_checkpoint_store.py``). LangGraph has no official SQL Server saver,
so the SQL path implements ``BaseCheckpointSaver`` on SQLAlchemy.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from voice_enable_mcp.storage.db import ensure_schema, get_session_factory
from voice_enable_mcp.storage.models import LgCheckpoint, LgCheckpointBlob, LgCheckpointWrite


def _version_key(version: Any) -> str:
    return str(version)


class SqlAlchemyCheckpointSaver(BaseCheckpointSaver[str]):
    """Durable LangGraph checkpointer using SQLite or Azure SQL."""

    def __init__(
        self,
        *,
        sqlite_path: Path | None = None,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self._sqlite_path = sqlite_path
        ensure_schema(sqlite_path=sqlite_path)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        factory = get_session_factory(sqlite_path=self._sqlite_path)
        session = factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    def _load_blobs(
        self,
        session: Session,
        thread_id: str,
        checkpoint_ns: str,
        versions: ChannelVersions,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for channel, version in versions.items():
            row = session.get(
                LgCheckpointBlob,
                (thread_id, checkpoint_ns, channel, _version_key(version)),
            )
            if row is None or row.blob_type == "empty" or row.blob is None:
                continue
            result[channel] = self.serde.loads_typed((row.blob_type, row.blob))
        return result

    def _pending_writes(
        self, session: Session, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> list[tuple[str, str, Any]]:
        rows = session.scalars(
            select(LgCheckpointWrite).where(
                LgCheckpointWrite.thread_id == thread_id,
                LgCheckpointWrite.checkpoint_ns == checkpoint_ns,
                LgCheckpointWrite.checkpoint_id == checkpoint_id,
            )
        ).all()
        writes: list[tuple[str, str, Any]] = []
        for row in rows:
            blob = b"" if row.blob is None else row.blob
            writes.append(
                (row.task_id, row.channel, self.serde.loads_typed((row.blob_type, blob)))
            )
        return writes

    def _row_to_tuple(self, session: Session, row: LgCheckpoint) -> CheckpointTuple:
        checkpoint: Checkpoint = self.serde.loads_typed(
            (row.checkpoint_type, row.checkpoint_blob)
        )
        metadata = self.serde.loads_typed((row.metadata_type, row.metadata_blob))
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": row.thread_id,
                    "checkpoint_ns": row.checkpoint_ns,
                    "checkpoint_id": row.checkpoint_id,
                }
            },
            checkpoint={
                **checkpoint,
                "channel_values": self._load_blobs(
                    session, row.thread_id, row.checkpoint_ns, checkpoint["channel_versions"]
                ),
            },
            metadata=metadata,
            pending_writes=self._pending_writes(
                session, row.thread_id, row.checkpoint_ns, row.checkpoint_id
            ),
            parent_config=(
                {
                    "configurable": {
                        "thread_id": row.thread_id,
                        "checkpoint_ns": row.checkpoint_ns,
                        "checkpoint_id": row.parent_checkpoint_id,
                    }
                }
                if row.parent_checkpoint_id
                else None
            ),
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "") or ""
        checkpoint_id = get_checkpoint_id(config)
        with self._session() as session:
            if checkpoint_id:
                row = session.get(LgCheckpoint, (thread_id, checkpoint_ns, checkpoint_id))
            else:
                row = session.scalars(
                    select(LgCheckpoint)
                    .where(
                        LgCheckpoint.thread_id == thread_id,
                        LgCheckpoint.checkpoint_ns == checkpoint_ns,
                    )
                    .order_by(desc(LgCheckpoint.checkpoint_id))
                    .limit(1)
                ).first()
            if row is None:
                return None
            return self._row_to_tuple(session, row)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"] if config else None
        config_checkpoint_ns = (
            config["configurable"].get("checkpoint_ns") if config else None
        )
        config_checkpoint_id = get_checkpoint_id(config) if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None

        with self._session() as session:
            stmt = select(LgCheckpoint).order_by(desc(LgCheckpoint.checkpoint_id))
            if thread_id is not None:
                stmt = stmt.where(LgCheckpoint.thread_id == thread_id)
            if config_checkpoint_ns is not None:
                stmt = stmt.where(LgCheckpoint.checkpoint_ns == (config_checkpoint_ns or ""))
            rows = list(session.scalars(stmt).all())
            remaining = limit
            for row in rows:
                if config_checkpoint_id and row.checkpoint_id != config_checkpoint_id:
                    continue
                if before_checkpoint_id and row.checkpoint_id >= before_checkpoint_id:
                    continue
                tup = self._row_to_tuple(session, row)
                if filter and not all(
                    query_value == tup.metadata.get(query_key)
                    for query_key, query_value in filter.items()
                ):
                    continue
                if remaining is not None:
                    if remaining <= 0:
                        break
                    remaining -= 1
                yield tup

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        copied = checkpoint.copy()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "") or ""
        values: dict[str, Any] = copied.pop("channel_values")  # type: ignore[misc]
        ckpt_type, ckpt_blob = self.serde.dumps_typed(copied)
        meta_type, meta_blob = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        parent_id = config["configurable"].get("checkpoint_id")

        with self._session() as session:
            for channel, version in new_versions.items():
                if channel in values:
                    blob_type, blob = self.serde.dumps_typed(values[channel])
                else:
                    blob_type, blob = "empty", None
                session.merge(
                    LgCheckpointBlob(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        channel=channel,
                        version=_version_key(version),
                        blob_type=blob_type,
                        blob=blob,
                    )
                )
            session.merge(
                LgCheckpoint(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint["id"],
                    parent_checkpoint_id=parent_id,
                    checkpoint_type=ckpt_type,
                    checkpoint_blob=ckpt_blob,
                    metadata_type=meta_type,
                    metadata_blob=meta_blob,
                )
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "") or ""
        checkpoint_id = config["configurable"]["checkpoint_id"]
        with self._session() as session:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                if write_idx >= 0:
                    existing = session.get(
                        LgCheckpointWrite,
                        (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx),
                    )
                    if existing is not None:
                        continue
                blob_type, blob = self.serde.dumps_typed(value)
                session.merge(
                    LgCheckpointWrite(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        idx=write_idx,
                        channel=channel,
                        blob_type=blob_type,
                        blob=blob,
                        task_path=task_path or "",
                    )
                )

    def delete_thread(self, thread_id: str) -> None:
        with self._session() as session:
            session.execute(delete(LgCheckpointWrite).where(LgCheckpointWrite.thread_id == thread_id))
            session.execute(delete(LgCheckpointBlob).where(LgCheckpointBlob.thread_id == thread_id))
            session.execute(delete(LgCheckpoint).where(LgCheckpoint.thread_id == thread_id))

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)
