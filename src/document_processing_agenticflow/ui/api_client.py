"""HTTP client helpers for the Gradio UI → FastAPI backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from document_processing_agenticflow.core.settings import settings


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _base_url() -> str:
    return settings().api_base_url.rstrip("/")


def check_health() -> dict[str, Any]:
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/health")
    if resp.status_code != 200:
        raise ApiError(f"Health check failed: {resp.text}", resp.status_code)
    return resp.json()


def transcribe_audio_file(
    audio_path: str | Path,
    *,
    language: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    path = Path(audio_path)
    if not path.exists():
        raise ApiError(f"Audio file not found: {path}")

    data: dict[str, str] = {}
    if language:
        data["language"] = language
    if provider and provider not in {"default", "auto"}:
        data["provider"] = provider

    with path.open("rb") as fh:
        files = {"audio": (path.name, fh, "audio/wav")}
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{_base_url()}/api/v1/audio/transcribe", files=files, data=data)

    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise ApiError(str(detail), resp.status_code)

    return resp.json()


def run_voice_contract_text(transcript: str, *, auto_create: bool = False) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_base_url()}/api/v1/voice/contract",
            json={"transcript": transcript, "auto_create": auto_create},
        )
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def confirm_voice_contract(
    legal_entity: str,
    contract_reference_number: str,
    *,
    transcript: str | None = None,
    thread_id: str | None = None,
    user_text: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "legal_entity": legal_entity,
        "contract_reference_number": contract_reference_number,
    }
    if transcript:
        payload["transcript"] = transcript
    if thread_id:
        payload["thread_id"] = thread_id
    if user_text:
        payload["user_text"] = user_text
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{_base_url()}/api/v1/voice/contract/confirm", json=payload)
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def run_voice_contract_audio(
    audio_path: str | Path,
    *,
    language: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    path = Path(audio_path)
    if not path.exists():
        raise ApiError(f"Audio file not found: {path}")

    data: dict[str, str] = {}
    if language:
        data["language"] = language
    if provider and provider not in {"default", "auto"}:
        data["provider"] = provider

    with path.open("rb") as fh:
        files = {"audio": (path.name, fh, "audio/wav")}
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{_base_url()}/api/v1/voice/contract/from-audio",
                files=files,
                data=data,
            )

    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise ApiError(str(detail), resp.status_code)

    return resp.json()


def create_document_job(
    template_path: str | Path,
    data: dict[str, Any] | str | Path,
    *,
    skip_validation: bool = False,
    max_retries: int = 1,
    validation_threshold: float = 0.7,
) -> dict[str, Any]:
    tpl = Path(template_path)
    if not tpl.exists():
        raise ApiError(f"Template not found: {tpl}")

    form_data = {
        "skip_validation": str(skip_validation).lower(),
        "max_retries": str(max_retries),
        "validation_threshold": str(validation_threshold),
    }

    files: dict[str, tuple] = {
        "template": (tpl.name, tpl.read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }

    if isinstance(data, (str, Path)) and Path(data).exists():
        p = Path(data)
        files["data_json"] = (p.name, p.read_bytes(), "application/json")
    elif isinstance(data, dict):
        form_data["data"] = json.dumps(data)
    else:
        raise ApiError("Provide JSON dict or a .json file path")

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f"{_base_url()}/api/v1/documents/jobs", files=files, data=form_data)

    if resp.status_code != 202:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def _ws_base_url() -> str:
    base = _base_url()
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :]
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :]
    return base


def iter_job_progress(
    job_id: str,
    *,
    timeout: float = 180.0,
    ws_url: str | None = None,
):
    """Yield live stage events from ``WS /documents/jobs/{id}/ws``."""
    from websockets.sync.client import connect

    path = ws_url or f"/api/v1/documents/jobs/{job_id}/ws"
    if path.startswith("ws://") or path.startswith("wss://"):
        url = path
    elif path.startswith("http://") or path.startswith("https://"):
        url = path.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    else:
        url = f"{_ws_base_url()}{path if path.startswith('/') else '/' + path}"

    with connect(url, open_timeout=15, close_timeout=5) as ws:
        # websockets recv timeout: use connection-level deadline via remaining time
        import time

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ApiError(f"Timed out waiting for job {job_id} over WebSocket")
            try:
                raw = ws.recv(timeout=min(remaining, 30.0))
            except TimeoutError as exc:
                raise ApiError(f"Timed out waiting for job {job_id} over WebSocket") from exc
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            event = json.loads(raw)
            yield event
            if event.get("terminal") or event.get("stage") in {"completed", "failed"}:
                return


def get_job_status(job_id: str, *, wait: bool = False, timeout: float = 180.0) -> dict[str, Any]:
    """Fetch job status. With wait=True, one long-poll request until terminal/timeout."""
    params: dict[str, Any] = {}
    if wait:
        params["wait"] = "true"
        params["timeout"] = timeout
    http_timeout = (timeout + 30.0) if wait else 30.0
    with httpx.Client(timeout=http_timeout) as client:
        resp = client.get(
            f"{_base_url()}/api/v1/documents/jobs/{job_id}",
            params=params or None,
        )
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def wait_for_job(
    job_id: str,
    *,
    timeout: float = 180.0,
    poll_seconds: float | None = None,
    ws_url: str | None = None,
    on_event: Any | None = None,
) -> dict[str, Any]:
    """Wait for job completion via WebSocket stages (falls back to long-poll).

    ``poll_seconds`` is accepted for backward compatibility and ignored.
    ``on_event`` is an optional callable(event_dict) for UI progress updates.
    """
    del poll_seconds
    stages: list[dict[str, Any]] = []
    try:
        for event in iter_job_progress(job_id, timeout=timeout, ws_url=ws_url):
            stages.append(event)
            if on_event is not None:
                on_event(event)
    except Exception:
        # Fallback: single long-poll GET (no continuous client polling).
        status = get_job_status(job_id, wait=True, timeout=timeout)
        if status.get("status") not in ("completed", "failed"):
            raise ApiError(
                f"Timed out waiting for job {job_id}. Last status: {status.get('status')}"
            )
        status["stages"] = stages
        return status

    status = get_job_status(job_id)
    status["stages"] = stages
    if status.get("status") not in ("completed", "failed"):
        # Terminal WS event without SQLite catch-up yet — brief long-poll.
        status = get_job_status(job_id, wait=True, timeout=min(30.0, timeout))
        status["stages"] = stages
    return status


def download_job_output(job_id: str, dest: Path) -> Path:
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/documents/jobs/{job_id}/download")
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def get_trace_by_xid(xid: str) -> dict[str, Any]:
    corr = (xid or "").strip()
    if not corr:
        raise ApiError("xid is required")
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/traces/{corr}")
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def list_document_jobs(limit: int = 20) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/api/v1/documents/jobs",
            params={"limit": max(1, min(int(limit), 100))},
        )
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()
