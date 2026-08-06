"""HTTP client helpers for the Gradio UI → FastAPI backend."""

from __future__ import annotations

import json
import time
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


def get_job_status(job_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/documents/jobs/{job_id}")
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def wait_for_job(job_id: str, *, poll_seconds: float = 1.0, timeout: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = get_job_status(job_id)
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(poll_seconds)
    raise ApiError(f"Timed out waiting for job {job_id}. Last status: {last.get('status')}")


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
