"""In-process job progress pub/sub for WebSocket clients (no Redis/Kafka).

Works for a single FastAPI process. Background job threads publish; WebSocket
handlers subscribe via asyncio queues.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

# Human-facing labels for LangGraph ``state["status"]`` values.
STAGE_META: dict[str, tuple[str, float]] = {
    "accepted": ("Job accepted", 0.0),
    "pending": ("Job pending", 0.02),
    "started": ("Pipeline started", 0.05),
    "processing": ("Processing document job", 0.08),
    "data_loaded": ("JSON data loaded", 0.12),
    "styles_extracted": ("Document template extraction done", 0.28),
    "extraction_validated": ("Extraction confidence scored", 0.40),
    "extraction_validation_skipped": ("Extraction validation skipped", 0.40),
    "fields_mapped": ("Fields mapped from JSON", 0.55),
    "document_generated": ("Styled Word document generated", 0.70),
    "validated": ("Document validation finished", 0.88),
    "retrying": ("Retrying map/generate after validation", 0.50),
    "finalizing": ("Finalizing job result", 0.95),
    "completed": ("Job completed", 1.0),
    "failed": ("Job failed", 1.0),
}

_TERMINAL = frozenset({"completed", "failed"})


@dataclass
class JobEvent:
    job_id: str
    stage: str
    message: str
    progress: float
    xid: str | None = None
    error: str | None = None
    terminal: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "stage": self.stage,
            "message": self.message,
            "progress": round(float(self.progress), 3),
            "terminal": self.terminal,
        }
        if self.xid:
            payload["xid"] = self.xid
        if self.error:
            payload["error"] = self.error
        if self.extra:
            payload["extra"] = self.extra
        return payload


class JobEventHub:
    """Thread-safe fan-out of job stage events to WebSocket subscribers."""

    def __init__(self, *, history_limit: int = 48) -> None:
        self._lock = Lock()
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._history_limit = history_limit
        self._loop: asyncio.AbstractEventLoop | None = None

    def publish(
        self,
        job_id: str,
        stage: str,
        *,
        message: str | None = None,
        progress: float | None = None,
        xid: str | None = None,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta_msg, meta_progress = STAGE_META.get(stage, (stage.replace("_", " ").title(), 0.5))
        event = JobEvent(
            job_id=job_id,
            stage=stage,
            message=message or meta_msg,
            progress=meta_progress if progress is None else progress,
            xid=xid,
            error=error,
            terminal=stage in _TERMINAL,
            extra=extra or {},
        )
        payload = event.to_dict()

        with self._lock:
            hist = self._history[job_id]
            hist.append(payload)
            if len(hist) > self._history_limit:
                del hist[: len(hist) - self._history_limit]
            queues = list(self._queues.get(job_id, []))
            loop = self._loop

        for queue in queues:
            self._enqueue(queue, payload, loop)
        return payload

    def _enqueue(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        payload: dict[str, Any],
        loop: asyncio.AbstractEventLoop | None,
    ) -> None:
        def _put() -> None:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

        if loop is not None and loop.is_running():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                _put()
            else:
                loop.call_soon_threadsafe(_put)
        else:
            _put()

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield historical then live events until a terminal stage."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._queues[job_id].append(queue)
            history = list(self._history.get(job_id, []))

        try:
            seen_terminal = False
            for item in history:
                yield item
                if item.get("terminal") or item.get("stage") in _TERMINAL:
                    seen_terminal = True
                    break
            if seen_terminal:
                return

            while True:
                item = await queue.get()
                yield item
                if item.get("terminal") or item.get("stage") in _TERMINAL:
                    return
        finally:
            with self._lock:
                live = self._queues.get(job_id) or []
                if queue in live:
                    live.remove(queue)
                if not live:
                    self._queues.pop(job_id, None)

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._history.pop(job_id, None)
            self._queues.pop(job_id, None)


_hub = JobEventHub()


def get_job_event_hub() -> JobEventHub:
    return _hub


def publish_job_stage(
    job_id: str,
    stage: str,
    *,
    message: str | None = None,
    progress: float | None = None,
    xid: str | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_job_event_hub().publish(
        job_id,
        stage,
        message=message,
        progress=progress,
        xid=xid,
        error=error,
        extra=extra,
    )
