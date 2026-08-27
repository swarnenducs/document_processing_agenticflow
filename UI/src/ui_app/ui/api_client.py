"""HTTP client helpers for the Gradio UI → FastAPI backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from ui_app.core.ui_config import get_admin_api_key, get_api_base_url

LIBRARY_TEMPLATE_FOLDER = "ipp_pricing_default_template"


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _base_url() -> str:
    return get_api_base_url()


def _admin_headers() -> dict[str, str]:
    key = get_admin_api_key()
    if not key:
        raise ApiError(
            "Admin API key is empty. Set admin_api_key in the API targets JSON "
            "(same value as ADMIN_API_KEY on the API), or set ADMIN_API_KEY in .env."
        )
    return {"X-Admin-Api-Key": key}


def check_health() -> dict[str, Any]:
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/health")
    if resp.status_code != 200:
        raise ApiError(f"Health check failed: {resp.text}", resp.status_code)
    return resp.json()


def check_maf_health() -> dict[str, Any]:
    """Central agent (MAF) readiness via API gateway ``GET /api/ask/health``."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{_base_url()}/api/ask/health")
    if resp.status_code >= 500:
        raise ApiError(f"MAF health check failed: {resp.text}", resp.status_code)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"ok": resp.status_code < 400, "raw": resp.text}


def ask_central_agent(
    message: str | None = None,
    *,
    instructions: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    role: str | None = None,
    persona: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Natural-language ask → MAF orchestrator via ``POST /api/ask``."""
    payload: dict[str, Any] = {}
    question = (prompt or message or "").strip()
    if question:
        payload["Prompt"] = question
    if instructions and instructions.strip():
        payload["instructions"] = instructions.strip()
    if session_id:
        payload["session_id"] = session_id
    if user_id:
        payload["user_id"] = user_id
    if user_email:
        payload["user_email"] = user_email
    persona_val = (persona or role or "").strip()
    if persona_val:
        payload["Persona"] = persona_val
    with httpx.Client(timeout=320.0) as client:
        resp = client.post(f"{_base_url()}/api/ask", json=payload)
    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise ApiError(str(detail), resp.status_code)
    return resp.json()


def list_central_agent_prompts() -> dict[str, Any]:
    """Validator path and min confidence via ``GET /api/ask/prompts``."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{_base_url()}/api/ask/prompts")
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def list_maf_mcp_tools() -> dict[str, Any]:
    """Tools available to the central agent (from both MCP servers)."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/agents/tools")
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
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


def run_voice_contract_text(
    transcript: str,
    *,
    auto_create: bool = False,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"transcript": transcript, "auto_create": auto_create}
    if session_id:
        payload["session_id"] = session_id
    if user_id:
        payload["user_id"] = user_id
    if user_email:
        payload["user_email"] = user_email
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{_base_url()}/api/v1/voice/contract", json=payload)
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
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
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
    if session_id:
        payload["session_id"] = session_id
    if user_id:
        payload["user_id"] = user_id
    if user_email:
        payload["user_email"] = user_email
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
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    path = Path(audio_path)
    if not path.exists():
        raise ApiError(f"Audio file not found: {path}")

    data: dict[str, str] = {}
    if language:
        data["language"] = language
    if provider and provider not in {"default", "auto"}:
        data["provider"] = provider
    if session_id:
        data["session_id"] = session_id
    if user_id:
        data["user_id"] = user_id
    if user_email:
        data["user_email"] = user_email

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
    template_path: str | Path | None,
    data: dict[str, Any] | str | Path,
    *,
    folder_name: str | None = None,
    template_name: str | None = None,
    skip_validation: bool = False,
    max_retries: int | None = None,
    validation_threshold: float | None = None,
    optimized_flow: bool = False,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    from ui_app.flow_debug import flow_breakpoint

    named = (template_name or "").strip()
    flow_breakpoint(
        "ui_create_document_job",
        template_path=str(template_path or ""),
        template_name=named,
    )

    form_data: dict[str, str] = {
        "skip_validation": str(skip_validation).lower(),
        "optimized_flow": str(optimized_flow).lower(),
    }
    if max_retries is not None:
        form_data["max_retries"] = str(max_retries)
    if validation_threshold is not None:
        form_data["validation_threshold"] = str(validation_threshold)
    if session_id:
        form_data["session_id"] = session_id
    if user_id:
        form_data["user_id"] = user_id
    if user_email:
        form_data["user_email"] = user_email

    files: dict[str, tuple] | None = None
    if named:
        form_data["template_name"] = named
        form_data["folder_name"] = (folder_name or "").strip() or LIBRARY_TEMPLATE_FOLDER
    else:
        if template_path is None:
            raise ApiError("Upload a .docx or choose a library template")
        tpl = Path(template_path)
        if not tpl.exists():
            raise ApiError(f"Template not found: {tpl}")
        files = {
            "template": (
                tpl.name,
                tpl.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        }

    if isinstance(data, dict):
        payload = data
    elif isinstance(data, (str, Path)) and Path(data).exists():
        try:
            payload = json.loads(Path(data).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON: {exc}") from exc
    elif isinstance(data, str):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON: {exc}") from exc
    else:
        raise ApiError("Provide JSON as a dict or JSON string in the request")
    if not isinstance(payload, dict):
        raise ApiError("JSON root must be an object")
    form_data["data"] = json.dumps(payload)

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{_base_url()}/api/v1/documents/jobs",
            files=files,
            data=form_data,
        )

    if resp.status_code != 202:
        detail = resp.text
        try:
            body = resp.json()
            detail = body.get("detail", detail)
            if isinstance(detail, list):
                detail = "; ".join(
                    str(item.get("msg") if isinstance(item, dict) else item) for item in detail
                )
        except Exception:  # noqa: BLE001
            pass
        raise ApiError(str(detail), resp.status_code)
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


def download_accuracy_pdf(job_id: str, dest: Path) -> Path:
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/documents/jobs/{job_id}/accuracy.pdf")
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


def _raise_for_status(resp: httpx.Response, *, ok: set[int] | None = None) -> None:
    allowed = ok or {200}
    if resp.status_code in allowed:
        return
    detail = resp.text
    try:
        parsed = resp.json()
        detail = parsed.get("detail", detail)
        if isinstance(detail, list):
            detail = "; ".join(
                str(item.get("msg") if isinstance(item, dict) else item) for item in detail
            )
    except Exception:  # noqa: BLE001
        pass
    raise ApiError(str(detail), resp.status_code)


def list_library_templates(*, folder_name: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    folder = (folder_name or "").strip() or LIBRARY_TEMPLATE_FOLDER
    params["folder_name"] = folder
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{_base_url()}/api/v1/documents/templates", params=params)
    if resp.status_code != 200:
        raise ApiError(resp.text, resp.status_code)
    return resp.json()


def list_admin_templates(*, folder_name: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    if folder_name:
        params["folder_name"] = folder_name
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/api/v1/admin/templates",
            headers=_admin_headers(),
            params=params or None,
        )
    _raise_for_status(resp)
    return resp.json()


def upload_admin_template(
    template_path: str | Path,
    *,
    folder_name: str = LIBRARY_TEMPLATE_FOLDER,
    template_name: str | None = None,
) -> dict[str, Any]:
    path = Path(template_path)
    if not path.exists():
        raise ApiError(f"Template not found: {path}")
    data: dict[str, str] = {"folder_name": folder_name}
    if template_name:
        data["template_name"] = template_name
    with path.open("rb") as fh:
        files = {
            "file": (
                path.name,
                fh,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{_base_url()}/api/v1/admin/templates",
                headers=_admin_headers(),
                data=data,
                files=files,
            )
    _raise_for_status(resp, ok={200, 201})
    return resp.json()


def list_master_data(*, category: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    if category:
        params["category"] = category
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/api/v1/admin/master-data",
            headers=_admin_headers(),
            params=params or None,
        )
    _raise_for_status(resp)
    return resp.json()


def upsert_master_data(
    *,
    placeholder_key: str,
    content: str,
    category: str | None = None,
    active: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "placeholder_key": placeholder_key,
        "content": content,
        "active": active,
    }
    if category:
        payload["category"] = category
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_base_url()}/api/v1/admin/master-data",
            headers=_admin_headers(),
            json=payload,
        )
    _raise_for_status(resp, ok={200, 201})
    return resp.json()


def delete_master_data(placeholder_key: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.delete(
            f"{_base_url()}/api/v1/admin/master-data/{placeholder_key}",
            headers=_admin_headers(),
        )
    _raise_for_status(resp)
    return resp.json()
