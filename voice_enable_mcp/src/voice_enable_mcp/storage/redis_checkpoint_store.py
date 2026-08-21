"""LangGraph checkpointer backed by Redis (vanilla Redis / Azure Cache).

Swap with SQL via ``LANGGRAPH_CHECKPOINT_BACKEND=redis`` and ``REDIS_URL``.
Uses plain keys — no RediSearch — so Azure Cache for Redis Basic works.

This is not ``langgraph-checkpoint-redis`` (that package needs Redis Stack).
"""

from __future__ import annotations

import base64
import json
import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any
from urllib.parse import quote

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


def _version_key(version: Any) -> str:
    return str(version)


def _b64(blob: bytes | None) -> str:
    return base64.b64encode(blob or b"").decode("ascii")


def _unb64(raw: str | None) -> bytes:
    if not raw:
        return b""
    return base64.b64decode(raw.encode("ascii"))


class RedisCheckpointSaver(BaseCheckpointSaver[str]):
    """Durable LangGraph checkpointer using Redis hashes + indexes."""

    def __init__(
        self,
        *,
        client: Any,
        prefix: str = "lg",
        ttl_seconds: int | None = None,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.client = client
        self.prefix = prefix.strip(":") or "lg"
        self.ttl_seconds = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        prefix: str = "lg",
        ttl_seconds: int | None = None,
        serde: SerializerProtocol | None = None,
    ) -> RedisCheckpointSaver:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        return cls(client=client, prefix=prefix, ttl_seconds=ttl_seconds, serde=serde)

    def _part(self, value: str) -> str:
        return quote(value, safe="")

    def _k(self, *parts: str) -> str:
        return self.prefix + ":" + ":".join(self._part(p) for p in parts)

    def _expire(self, *keys: str) -> None:
        if self.ttl_seconds is None:
            return
        pipe = self.client.pipeline()
        for key in keys:
            pipe.expire(key, self.ttl_seconds)
        pipe.execute()

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

    def _ckpt_key(self, thread_id: str, ns: str, checkpoint_id: str) -> str:
        return self._k("ckpt", thread_id, ns, checkpoint_id)

    def _ckpt_index(self, thread_id: str, ns: str) -> str:
        return self._k("idx", "ckpt", thread_id, ns)

    def _blob_key(self, thread_id: str, ns: str, channel: str, version: str) -> str:
        return self._k("blob", thread_id, ns, channel, version)

    def _blob_index(self, thread_id: str) -> str:
        return self._k("idx", "blob", thread_id)

    def _write_key(
        self, thread_id: str, ns: str, checkpoint_id: str, task_id: str, idx: int
    ) -> str:
        return self._k("write", thread_id, ns, checkpoint_id, task_id, str(idx))

    def _write_index(self, thread_id: str, ns: str, checkpoint_id: str) -> str:
        return self._k("idx", "write", thread_id, ns, checkpoint_id)

    def _ns_index(self, thread_id: str) -> str:
        return self._k("idx", "ns", thread_id)

    def _threads_key(self) -> str:
        return self._k("threads")

    def _load_blobs(self, thread_id: str, ns: str, versions: ChannelVersions) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for channel, version in versions.items():
            raw = self.client.get(self._blob_key(thread_id, ns, channel, _version_key(version)))
            if not raw:
                continue
            payload = json.loads(raw)
            if payload.get("t") == "empty":
                continue
            result[channel] = self.serde.loads_typed((payload["t"], _unb64(payload.get("b"))))
        return result

    def _pending_writes(
        self, thread_id: str, ns: str, checkpoint_id: str
    ) -> list[tuple[str, str, Any]]:
        members = self.client.smembers(self._write_index(thread_id, ns, checkpoint_id)) or []
        writes: list[tuple[str, str, Any]] = []
        for member in members:
            task_id, _, idx_s = member.partition("\x1f")
            raw = self.client.get(self._write_key(thread_id, ns, checkpoint_id, task_id, int(idx_s)))
            if not raw:
                continue
            payload = json.loads(raw)
            writes.append(
                (
                    payload["task_id"],
                    payload["channel"],
                    self.serde.loads_typed((payload["t"], _unb64(payload.get("b")))),
                )
            )
        return writes

    def _row_to_tuple(
        self, thread_id: str, ns: str, checkpoint_id: str, payload: dict[str, Any]
    ) -> CheckpointTuple:
        checkpoint: Checkpoint = self.serde.loads_typed(
            (payload["ckpt_t"], _unb64(payload["ckpt_b"]))
        )
        metadata = self.serde.loads_typed((payload["meta_t"], _unb64(payload["meta_b"])))
        parent_id = payload.get("parent") or None
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint={
                **checkpoint,
                "channel_values": self._load_blobs(thread_id, ns, checkpoint["channel_versions"]),
            },
            metadata=metadata,
            pending_writes=self._pending_writes(thread_id, ns, checkpoint_id),
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": ns,
                        "checkpoint_id": parent_id,
                    }
                }
                if parent_id
                else None
            ),
        )

    def _load_checkpoint(
        self, thread_id: str, ns: str, checkpoint_id: str
    ) -> CheckpointTuple | None:
        raw = self.client.get(self._ckpt_key(thread_id, ns, checkpoint_id))
        if not raw:
            return None
        return self._row_to_tuple(thread_id, ns, checkpoint_id, json.loads(raw))

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id: str = config["configurable"]["thread_id"]
        ns: str = config["configurable"].get("checkpoint_ns", "") or ""
        checkpoint_id = get_checkpoint_id(config)
        if checkpoint_id:
            return self._load_checkpoint(thread_id, ns, checkpoint_id)
        latest = self.client.zrevrange(self._ckpt_index(thread_id, ns), 0, 0)
        if not latest:
            return None
        return self._load_checkpoint(thread_id, ns, latest[0])

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"] if config else None
        config_ns = config["configurable"].get("checkpoint_ns") if config else None
        config_checkpoint_id = get_checkpoint_id(config) if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None

        thread_ids: Sequence[str]
        if thread_id is not None:
            thread_ids = (thread_id,)
        else:
            thread_ids = tuple(self.client.smembers(self._threads_key()) or [])

        remaining = limit
        for tid in thread_ids:
            if config_ns is not None:
                namespaces = (config_ns or "",)
            else:
                namespaces = tuple(self.client.smembers(self._ns_index(tid)) or [""])
            for ns in namespaces:
                ids = self.client.zrevrange(self._ckpt_index(tid, ns), 0, -1) or []
                for checkpoint_id in ids:
                    if config_checkpoint_id and checkpoint_id != config_checkpoint_id:
                        continue
                    if before_checkpoint_id and checkpoint_id >= before_checkpoint_id:
                        continue
                    tup = self._load_checkpoint(tid, ns, checkpoint_id)
                    if tup is None:
                        continue
                    if filter and not all(
                        query_value == tup.metadata.get(query_key)
                        for query_key, query_value in filter.items()
                    ):
                        continue
                    if remaining is not None:
                        if remaining <= 0:
                            return
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
        ns = config["configurable"].get("checkpoint_ns", "") or ""
        values: dict[str, Any] = copied.pop("channel_values")  # type: ignore[misc]
        ckpt_type, ckpt_blob = self.serde.dumps_typed(copied)
        meta_type, meta_blob = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        parent_id = config["configurable"].get("checkpoint_id")
        checkpoint_id = checkpoint["id"]

        payload = json.dumps(
            {
                "parent": parent_id,
                "ckpt_t": ckpt_type,
                "ckpt_b": _b64(ckpt_blob),
                "meta_t": meta_type,
                "meta_b": _b64(meta_blob),
            }
        )
        ckpt_key = self._ckpt_key(thread_id, ns, checkpoint_id)
        idx_key = self._ckpt_index(thread_id, ns)
        ns_key = self._ns_index(thread_id)
        threads_key = self._threads_key()
        blob_idx = self._blob_index(thread_id)
        touch = [ckpt_key, idx_key, ns_key, threads_key, blob_idx]

        pipe = self.client.pipeline()
        for channel, version in new_versions.items():
            if channel in values:
                blob_type, blob = self.serde.dumps_typed(values[channel])
            else:
                blob_type, blob = "empty", None
            bkey = self._blob_key(thread_id, ns, channel, _version_key(version))
            pipe.set(
                bkey,
                json.dumps({"t": blob_type, "b": _b64(blob)}),
            )
            pipe.sadd(blob_idx, bkey)
            touch.append(bkey)
        pipe.set(ckpt_key, payload)
        pipe.zadd(idx_key, {checkpoint_id: 0})
        pipe.sadd(ns_key, ns)
        pipe.sadd(threads_key, thread_id)
        pipe.execute()
        self._expire(*touch)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint_id,
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
        ns = config["configurable"].get("checkpoint_ns", "") or ""
        checkpoint_id = config["configurable"]["checkpoint_id"]
        windex = self._write_index(thread_id, ns, checkpoint_id)
        touch = [windex]
        pipe = self.client.pipeline()
        for idx, (channel, value) in enumerate(writes):
            write_idx = WRITES_IDX_MAP.get(channel, idx)
            member = f"{task_id}\x1f{write_idx}"
            wkey = self._write_key(thread_id, ns, checkpoint_id, task_id, write_idx)
            if write_idx >= 0 and self.client.exists(wkey):
                continue
            blob_type, blob = self.serde.dumps_typed(value)
            pipe.set(
                wkey,
                json.dumps(
                    {
                        "task_id": task_id,
                        "channel": channel,
                        "task_path": task_path or "",
                        "t": blob_type,
                        "b": _b64(blob),
                    }
                ),
            )
            pipe.sadd(windex, member)
            touch.append(wkey)
        pipe.execute()
        self._expire(*touch)

    def delete_thread(self, thread_id: str) -> None:
        namespaces = list(self.client.smembers(self._ns_index(thread_id)) or [])
        keys: list[str] = [self._ns_index(thread_id), self._blob_index(thread_id)]
        keys.extend(self.client.smembers(self._blob_index(thread_id)) or [])
        for ns in namespaces:
            idx = self._ckpt_index(thread_id, ns)
            ids = list(self.client.zrange(idx, 0, -1) or [])
            keys.append(idx)
            for checkpoint_id in ids:
                keys.append(self._ckpt_key(thread_id, ns, checkpoint_id))
                windex = self._write_index(thread_id, ns, checkpoint_id)
                members = list(self.client.smembers(windex) or [])
                keys.append(windex)
                for member in members:
                    task_id, _, idx_s = member.partition("\x1f")
                    keys.append(
                        self._write_key(thread_id, ns, checkpoint_id, task_id, int(idx_s))
                    )
        if keys:
            self.client.delete(*keys)
        self.client.srem(self._threads_key(), thread_id)

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
