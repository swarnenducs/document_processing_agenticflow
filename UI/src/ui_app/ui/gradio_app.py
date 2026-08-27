"""Gradio UI — record voice, send to FastAPI, generate documents."""

from __future__ import annotations

import base64
import json
import logging
import re
import tempfile
from pathlib import Path

import gradio as gr

from ui_app.core.settings import settings
from ui_app.core.ui_config import get_api_base_url
from ui_app.ui.admin_ui import (
    ui_api_target_caption,
    ui_apply_api_config,
    ui_config_json,
    ui_delete_master,
    ui_list_master,
    ui_list_templates,
    ui_save_master,
    ui_upload_template,
)
from ui_app.ui.api_client import (
    ApiError,
    LIBRARY_TEMPLATE_FOLDER,
    ask_central_agent,
    check_health,
    check_maf_health,
    confirm_voice_contract,
    create_document_job,
    download_accuracy_pdf,
    download_job_output,
    get_job_status,
    get_trace_by_xid,
    list_document_jobs,
    list_library_templates,
    list_maf_mcp_tools,
    run_voice_contract_audio,
    run_voice_contract_text,
    wait_for_job,
)

logger = logging.getLogger(__name__)

LIBRARY_PLACEHOLDER = "— select a library template —"

# Allow: python -m ui_app.ui.gradio_app

_CONFIRM_HINTS = re.compile(
    r"^\s*(yes|y|ok|okay|confirm|proceed|create\s+it|go\s+ahead|select)\b",
    re.IGNORECASE,
)


def _is_confirmation(text: str) -> bool:
    return bool(_CONFIRM_HINTS.search(text or ""))


def _format_contract_ref(value: str) -> str:
    raw = (value or "").strip().upper()
    compact = re.sub(r"[\s\-_]+", "", raw)
    match = re.fullmatch(r"([A-Z]+)(\d+)", compact)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return raw or compact


def _resolve_gradio_path(value: object | None) -> str | None:
    """Normalize Gradio File/Audio return values to a local filepath."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list) and value:
        return _resolve_gradio_path(value[0])
    if isinstance(value, dict):
        path = value.get("path") or value.get("name")
        return str(path) if path else None
    path_attr = getattr(value, "path", None) or getattr(value, "name", None)
    if path_attr:
        return str(path_attr)
    return str(value)


def _assistant_from_result(result: dict) -> str:
    status = result.get("status")
    msg = result.get("message") or ""
    if status == "needs_confirmation":
        entity = result.get("legal_entity") or {}
        lines = [
            msg,
            "",
            f"- Legal entity: {entity.get('legalName')} ({entity.get('code')})",
            f"- Address: {entity.get('address')}",
            f"- Suggested reference: {result.get('contract_reference_number')}",
            "",
            "Type **yes** to confirm, or type the reference (e.g. `CR-1001`).",
        ]
        return "\n".join(lines)
    if status == "completed" or result.get("ok"):
        lines = [
            msg,
            "",
            "Dummy contract created.",
        ]
        if result.get("contract_id"):
            lines.append(f"SQLite contract id: `{result.get('contract_id')}`")
        if result.get("contract_text"):
            lines.extend(["", "```", result["contract_text"], "```"])
        return "\n".join(lines)
    err = result.get("error") or result.get("error_message")
    extra = [str(e) for e in (result.get("errors") or []) if e]
    if err or extra:
        lines = ["**Error**", "", msg or "The request failed."]
        if err:
            lines.append(str(err))
        lines.extend(extra)
        return "\n".join(line for line in lines if line is not None)
    return msg or "Please ask a relevant service."


def _run_contract_request(
    text: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> dict:
    """Voice contract start — HTTP to ip_api only (no local workflow)."""
    return run_voice_contract_text(
        text,
        auto_create=False,
        session_id=session_id,
        user_id=user_id,
        user_email=user_email,
    )


def _confirm_contract_request(
    legal_entity: str,
    contract_reference_number: str,
    *,
    transcript: str | None = None,
    thread_id: str | None = None,
    user_text: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> dict:
    """Voice contract confirm — HTTP to ip_api only (no local workflow)."""
    return confirm_voice_contract(
        legal_entity,
        contract_reference_number,
        transcript=transcript,
        thread_id=thread_id,
        user_text=user_text,
        session_id=session_id,
        user_id=user_id,
        user_email=user_email,
    )


def ui_contract_chat(
    message: str,
    history: list[dict[str, str]] | None,
    pending: dict | None,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> tuple[list[dict[str, str]], dict | None, str | None, str | None, str | None]:
    """Chat-style human-in-the-loop contract creation."""
    history = list(history or [])
    pending = dict(pending or {})
    text = (message or "").strip()
    sid = (session_id or "").strip() or None
    uid = (user_id or "").strip() or None
    email = (user_email or "").strip() or None
    if not text:
        return history, pending, None, None, sid

    history.append({"role": "user", "content": text})

    try:
        # Confirmation turn
        if pending.get("awaiting_confirmation"):
            chosen_ref = pending.get("contract_reference_number")
            entity_key = pending.get("legal_entity_code") or pending.get("legal_entity_name")
            ref = chosen_ref if _is_confirmation(text) else _format_contract_ref(text)
            result = _confirm_contract_request(
                str(entity_key),
                str(ref),
                transcript=pending.get("transcript"),
                thread_id=pending.get("thread_id"),
                user_text=text,
                session_id=sid,
                user_id=uid,
                user_email=email,
            )
            sid = result.get("session_id") or sid
            history.append({"role": "assistant", "content": _assistant_from_result(result)})
            text_file = result.get("contract_text_file")
            docx_file = result.get("contract_file")
            if result.get("ok"):
                return history, {}, text_file, docx_file, sid
            return history, pending, None, None, sid

        # New request turn
        result = _run_contract_request(
            text, session_id=sid, user_id=uid, user_email=email
        )
        sid = result.get("session_id") or sid
        history.append({"role": "assistant", "content": _assistant_from_result(result)})

        if result.get("status") == "needs_confirmation":
            entity = result.get("legal_entity") or {}
            candidates = result.get("candidates") or []
            pending = {
                "awaiting_confirmation": True,
                "thread_id": result.get("thread_id"),
                "legal_entity_code": entity.get("code"),
                "legal_entity_name": entity.get("legalName") or result.get("legal_entity_name"),
                "contract_reference_number": result.get("contract_reference_number"),
                "candidate_refs": [
                    c.get("contractReferenceNumber")
                    for c in candidates
                    if c.get("contractReferenceNumber")
                ],
                "transcript": text,
            }
            return history, pending, None, None, sid

        if result.get("ok") and result.get("status") == "completed":
            return history, {}, result.get("contract_text_file"), result.get("contract_file"), sid

        return history, {}, None, None, sid
    except Exception as exc:  # noqa: BLE001
        history.append({"role": "assistant", "content": f"Error: {exc}"})
        return history, pending, None, None, sid


def ui_contract_chat_from_audio(
    audio_path: object | None,
    history: list[dict[str, str]] | None,
    pending: dict | None,
    language: str,
    provider: str,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> tuple[list[dict[str, str]], dict | None, str | None, str | None, str, str | None]:
    path = _resolve_gradio_path(audio_path)
    sid = (session_id or "").strip() or None
    uid = (user_id or "").strip() or None
    email = (user_email or "").strip() or None
    if not path:
        history = list(history or [])
        history.append(
            {
                "role": "assistant",
                "content": "Record or upload audio first, or type in the chat box.",
            }
        )
        return history, pending or {}, None, None, "", sid
    try:
        lang = language.strip() or None
        prov = None if provider in {"", "default", "auto"} else provider
        result = run_voice_contract_audio(
            path,
            language=lang,
            provider=prov,
            session_id=sid,
            user_id=uid,
            user_email=email,
        )
        sid = result.get("session_id") or sid
        transcript = result.get("transcript") or ""
        if not transcript:
            history = list(history or [])
            history.append(
                {
                    "role": "assistant",
                    "content": (
                        "Audio transcribed empty. Please type the instruction in chat, e.g.\n"
                        "`please create contract with legal entity AVC contract "
                        "reference number CR 1001`"
                    ),
                }
            )
            return history, pending or {}, None, None, "", sid
        new_history, new_pending, txt, docx, sid = ui_contract_chat(
            transcript, history, pending, sid, uid, email
        )
        return new_history, new_pending, txt, docx, transcript, sid
    except ApiError as exc:
        history = list(history or [])
        history.append(
            {
                "role": "assistant",
                "content": (
                    f"Speech transcription failed (`{exc}`).\n\n"
                    "Type the instruction in chat instead."
                ),
            }
        )
        return history, pending or {}, None, None, "", sid
    except Exception as exc:  # noqa: BLE001
        history = list(history or [])
        history.append(
            {
                "role": "assistant",
                "content": (
                    f"Speech error: {exc}\n\n"
                    "You can type the prompt in chat without microphone."
                ),
            }
        )
        return history, pending or {}, None, None, "", sid


def _resolve_json_payload(json_file: object | None, json_text: str) -> dict:
    """Build the JSON request payload. A local file is read here, never uploaded."""
    file_path = _resolve_gradio_path(json_file)
    if file_path:
        p = Path(file_path)
        if p.suffix.lower() != ".json":
            raise ValueError("Local JSON must be a `.json` file")
        payload = json.loads(p.read_text(encoding="utf-8"))
    elif json_text.strip():
        payload = json.loads(json_text)
    else:
        raise ValueError("Paste JSON in the request, or pick a local `.json` file to send as request data")

    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object `{}`")
    return payload


def _format_elapsed_ms(elapsed_ms: float) -> str:
    total_s = max(0.0, float(elapsed_ms) / 1000.0)
    if total_s < 60:
        return f"{total_s:.1f} s"
    minutes = int(total_s // 60)
    seconds = total_s - minutes * 60
    if minutes < 60:
        return f"{minutes}m {seconds:.1f}s"
    hours = minutes // 60
    minutes_rem = minutes % 60
    return f"{hours}h {minutes_rem}m {seconds:.0f}s"


def _coerce_elapsed_ms(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _overall_time_label(status: dict) -> str:
    """Human wall time from API elapsed / elapsed_ms / timestamps."""
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    acc = status.get("accuracy_report") if isinstance(status.get("accuracy_report"), dict) else {}
    conf = status.get("confidence") if isinstance(status.get("confidence"), dict) else {}
    for source in (status, result, acc, conf):
        if not isinstance(source, dict):
            continue
        human = source.get("elapsed")
        if isinstance(human, str) and human.strip() and human.strip() != "-":
            return human.strip()
        ms = _coerce_elapsed_ms(source.get("elapsed_ms"))
        if ms is not None:
            return _format_elapsed_ms(ms)

    created = str(status.get("created_at") or "").strip()
    completed = str(status.get("completed_at") or "").strip()
    if created and completed:
        from datetime import datetime

        try:
            start = datetime.fromisoformat(created.replace("Z", "+00:00"))
            end = datetime.fromisoformat(completed.replace("Z", "+00:00"))
            if start.tzinfo is None and end.tzinfo is not None:
                start = start.replace(tzinfo=end.tzinfo)
            elif end.tzinfo is None and start.tzinfo is not None:
                end = end.replace(tzinfo=start.tzinfo)
            if end >= start:
                return _format_elapsed_ms((end - start).total_seconds() * 1000.0)
        except (TypeError, ValueError):
            pass
    return ""


def _marker_detection_from_status(status: dict) -> dict | None:
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    acc = status.get("accuracy_report") if isinstance(status.get("accuracy_report"), dict) else {}
    for blob in (status, result, acc):
        if isinstance(blob, dict) and isinstance(blob.get("marker_detection"), dict):
            return blob["marker_detection"]
    return None


def _unmarked_template_report_rows(status: dict) -> list[list[str]]:
    detection = _marker_detection_from_status(status)
    if not isinstance(detection, dict) or detection.get("had_markers") is not False:
        return []
    match = detection.get("library_match")
    name = ""
    score = None
    if isinstance(match, dict):
        name = str(match.get("name") or "").strip()
        score = match.get("score")
    closest = name or "none found"
    if name and isinstance(score, (int, float)):
        closest = f"{name} (similarity {score:.4f})"
    return [
        ["Template markers", "<strong>Unmarked</strong>"],
        [
            "Processing note",
            "The template was unmarked, so the AI took extra time to understand the document.",
        ],
        ["Reference closest-match template", f"<code>{_html_esc(closest)}</code>"],
    ]


def _html_esc(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _as_score_pct(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _item_score_pct(item: dict) -> float | None:
    pct = _as_score_pct(item.get("confidence_pct"))
    if pct is not None:
        return pct
    pct = _as_score_pct(item.get("confidence"))
    if pct is not None and pct <= 1.0:
        return pct * 100.0
    return pct


def _score_badge(pct: float | None, *, strong: bool = False) -> str:
    """Color: red below 80%, green at or above 90%, amber between."""
    if pct is None:
        return '<span style="opacity:0.7">n/a</span>'
    text = f"{pct:.1f}%"
    if pct < 80:
        bg, fg = "#7f1d1d", "#fecaca"
    elif pct >= 90:
        bg, fg = "#14532d", "#bbf7d0"
    else:
        bg, fg = "#78350f", "#fde68a"
    weight = "800" if strong else "700"
    inner = f"<strong>{_html_esc(text)}</strong>" if strong else _html_esc(text)
    return (
        f'<span style="display:inline-block;min-width:4.4rem;text-align:center;'
        f"padding:0.2rem 0.55rem;border-radius:999px;background:{bg};color:{fg};"
        f'font-weight:{weight};letter-spacing:0.02em">{inner}</span>'
    )


def _error_banner(title: str, messages: list[str] | str) -> str:
    """Visible error panel for the Gradio HTML result box."""
    if isinstance(messages, str):
        lines = [messages]
    else:
        lines = [str(item) for item in messages if str(item).strip()]
    if not lines:
        lines = ["Unknown failure"]
    body = "<br>".join(_html_esc(line).replace("\n", "<br>") for line in lines)
    return f"""
<div style="margin:0 0 1rem 0;padding:0.85rem 1rem;border:1px solid #8a3030;
            border-radius:8px;background:#2a1212;color:#FFC4C4;line-height:1.5">
  <div style="font-weight:700;color:#FF9A9A;margin-bottom:0.35rem">{_html_esc(title)}</div>
  <div style="white-space:pre-wrap;word-break:break-word">{body}</div>
</div>
"""


def _job_error_messages(status: dict) -> list[str]:
    """Collect pipeline / judge / extraction errors from a job status payload."""
    seen: set[str] = set()
    texts: list[str] = []

    def _add(text: object) -> None:
        value = str(text or "").strip()
        if value and value not in seen:
            seen.add(value)
            texts.append(value)

    _add(status.get("error_message"))
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    _add(result.get("error"))
    for item in result.get("errors") or []:
        _add(item)
    for item in status.get("errors") or []:
        _add(item)

    validation = status.get("validation") if isinstance(status.get("validation"), dict) else {}
    if validation.get("passed") is False:
        _add(validation.get("summary") or "Document judge did not pass")
        for issue in (validation.get("issues") or [])[:8]:
            if not isinstance(issue, dict):
                _add(issue)
                continue
            field = issue.get("field") or ""
            message = issue.get("message") or ""
            severity = issue.get("severity") or "issue"
            _add(f"Judge {severity}: {field} — {message}".strip(" —"))

    extraction = status.get("extraction_validation")
    if isinstance(extraction, dict) and extraction.get("passed") is False:
        _add(extraction.get("summary") or "Extraction critic did not pass")
        for issue in (extraction.get("issues") or [])[:5]:
            if isinstance(issue, dict):
                _add(issue.get("message") or issue)
            else:
                _add(issue)
    return texts


def _build_failed_job_report(job_id: str, status: dict, stages: list[dict] | None = None) -> str:
    messages = _job_error_messages(status) or ["Unknown failure"]
    xid = status.get("xid") or ""
    elapsed = _overall_time_label(status) or "n/a"
    return (
        '<div style="font-size:0.95rem;line-height:1.4">'
        + _error_banner(f"Job {job_id} failed", messages)
        + f"""
<div style="margin:0 0 1rem 0;opacity:0.85;font-size:0.9rem">
  xid <code>{_html_esc(xid)}</code> · time {_html_esc(elapsed)}
</div>
"""
        + _stages_table_html(stages or [])
        + "</div>"
    ).replace("${", "$&#123;").replace("{{", "{&#123;")


_SPINNER_CSS = """
<style>
@keyframes docflow-spin { to { transform: rotate(360deg); } }
@keyframes docflow-pulse {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}
.docflow-loader {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin: 0 0 0.85rem 0;
  padding: 0.75rem 0.9rem;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  background: #1a1a1a;
}
.docflow-spinner {
  width: 1.35rem;
  height: 1.35rem;
  border: 3px solid #444;
  border-top-color: #7ec8ff;
  border-radius: 50%;
  animation: docflow-spin 0.8s linear infinite;
  flex-shrink: 0;
}
.docflow-loader-text { line-height: 1.35; }
.docflow-loader-title {
  font-weight: 600;
  animation: docflow-pulse 1.6s ease-in-out infinite;
}
.docflow-bar-wrap {
  margin: 0.55rem 0 0.85rem 0;
  height: 0.55rem;
  background: #2a2a2a;
  border-radius: 999px;
  overflow: hidden;
}
.docflow-bar {
  height: 100%;
  background: linear-gradient(90deg, #3d8bfd, #7ec8ff);
  border-radius: 999px;
  transition: width 0.35s ease;
}
</style>
"""


def _loading_html(message: str = "Starting document job…") -> str:
    """Shown immediately so the user knows work has begun."""
    return f"""
{_SPINNER_CSS}
<div class="docflow-loader">
  <div class="docflow-spinner" aria-hidden="true"></div>
  <div class="docflow-loader-text">
    <div class="docflow-loader-title">{_html_esc(message)}</div>
    <div style="opacity:0.8;font-size:0.9rem;margin-top:0.15rem">
      Please wait — pipeline stages will appear here live.
    </div>
  </div>
</div>
"""


def _append_ws_stage(stages: list[dict], event: dict) -> list[dict]:
    """Keep a unique chronological stage list (no snapshot / no duplicates)."""
    if not isinstance(event, dict):
        return stages
    if isinstance(event.get("extra"), dict) and event["extra"].get("source") == "snapshot":
        return stages
    stage = str(event.get("stage") or "").strip()
    if not stage:
        return stages
    msg = str(event.get("message") or "")
    if msg.lower().startswith("current status:"):
        return stages

    # Update in place if same stage already present; else append.
    for i, existing in enumerate(stages):
        if existing.get("stage") == stage:
            stages[i] = event
            return stages
    stages.append(event)
    return stages


def _stages_table_html(stages: list[dict]) -> str:
    if not stages:
        return (
            "<p style='opacity:0.75;margin:0.4rem 0'>Waiting for WebSocket stages…</p>"
        )
    rows: list[str] = []
    for event in stages:
        stage = str(event.get("stage") or "")
        msg = str(event.get("message") or stage)
        ev_pct = event.get("progress")
        pct_s = f"{float(ev_pct) * 100:.0f}%" if isinstance(ev_pct, (int, float)) else ""
        err = event.get("error")
        color = (
            "#FF9A9A"
            if stage == "failed"
            else "#9EF0B8"
            if stage == "completed"
            else "#CFCFCF"
        )
        detail = f" — {_html_esc(err)}" if err else ""
        rows.append(
            "<tr>"
            f"<td style='padding:0.3rem 0.5rem;color:{color}'><code>{_html_esc(stage)}</code></td>"
            f"<td style='padding:0.3rem 0.5rem'>{_html_esc(msg)}{detail}</td>"
            f"<td style='padding:0.3rem 0.5rem;opacity:0.8'>{_html_esc(pct_s)}</td>"
            "</tr>"
        )
    return f"""
<section style="margin:0.75rem 0 0 0">
  <h4 style="margin:0 0 0.4rem 0">Pipeline stages</h4>
  <table style="width:100%;border-collapse:collapse;font-size:0.92rem">
    <thead>
      <tr>
        <th style="text-align:left;padding:0.3rem 0.5rem;border-bottom:1px solid #3a3a3a">Stage</th>
        <th style="text-align:left;padding:0.3rem 0.5rem;border-bottom:1px solid #3a3a3a">Message</th>
        <th style="text-align:left;padding:0.3rem 0.5rem;border-bottom:1px solid #3a3a3a">%</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def _progress_html(job_id: str, stages: list[dict], *, working: bool = True) -> str:
    """Current status loader + unique WebSocket stage list."""
    latest = stages[-1] if stages else {}
    latest_stage = str(latest.get("stage") or "starting")
    latest_msg = str(latest.get("message") or "Waiting for first pipeline stage…")
    progress = latest.get("progress")
    pct = float(progress) if isinstance(progress, (int, float)) else 0.05
    pct = max(0.0, min(pct, 1.0))
    pct_label = f"{pct * 100:.0f}%"
    terminal = bool(latest.get("terminal") or latest_stage in {"completed", "failed"})
    failed = latest_stage == "failed"
    show_spinner = working and not terminal

    if failed:
        status_title = "Job failed"
        status_sub = _html_esc(latest.get("error") or latest_msg)
    elif terminal:
        status_title = "Job completed"
        status_sub = "Building final report…"
    else:
        status_title = f"In progress — {_html_esc(latest_msg)}"
        status_sub = (
            f"Stage <code>{_html_esc(latest_stage)}</code> · {_html_esc(pct_label)}"
        )

    spinner = (
        '<div class="docflow-spinner" aria-hidden="true"></div>' if show_spinner else ""
    )
    bar_color = "#FF9A9A" if failed else "#9EF0B8" if terminal else None
    bar_style = f"width:{pct * 100:.1f}%;"
    if bar_color:
        bar_style += f"background:{bar_color};"

    return f"""
{_SPINNER_CSS}
<div style="line-height:1.45">
  <div class="docflow-loader">
    {spinner}
    <div class="docflow-loader-text">
      <div class="docflow-loader-title">{status_title}</div>
      <div style="opacity:0.85;font-size:0.9rem;margin-top:0.15rem">{status_sub}</div>
      <div style="opacity:0.7;font-size:0.85rem;margin-top:0.25rem">
        Job <code>{_html_esc(job_id)}</code>
      </div>
    </div>
  </div>
  <div class="docflow-bar-wrap" title="{_html_esc(pct_label)}">
    <div class="docflow-bar" style="{bar_style}"></div>
  </div>
  {_stages_table_html(stages)}
</div>
"""


def _accuracy_pdf_panel(job_id: str, pdf_path: str | None = None) -> str:
    """Show the accuracy PDF in the job-result panel (viewer + download link)."""
    api = get_api_base_url().rstrip("/")
    href = f"{api}/api/v1/documents/jobs/{job_id}/accuracy.pdf"
    viewer = ""
    path = Path(pdf_path) if pdf_path else None
    if path is not None and path.is_file() and path.stat().st_size > 0:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        viewer = (
            f'<object data="data:application/pdf;base64,{b64}" type="application/pdf" '
            'style="width:100%;height:920px;border:1px solid #3a3a3a;border-radius:8px;'
            'background:#111">'
            f'<p style="padding:0.75rem"><a href="{_html_esc(href)}" target="_blank" '
            'rel="noopener">Open full accuracy PDF</a></p>'
            "</object>"
        )
    else:
        viewer = (
            f'<p style="padding:0.5rem 0"><a href="{_html_esc(href)}" target="_blank" '
            'rel="noopener">Open full accuracy report PDF</a> '
            "(same scores as the tables below)</p>"
        )
    fname = f"{job_id}.pdf"
    return f"""
<section style="margin:0 0 1rem 0;padding:0.85rem 1rem;border:1px solid #2a4a6b;
                border-radius:10px;background:#101820">
  <h4 style="margin:0 0 0.4rem 0">Full accuracy report PDF</h4>
  <p style="opacity:0.9;font-size:0.9rem;margin:0 0 0.5rem 0">
    File name: <code>{_html_esc(fname)}</code>
    · <a href="{_html_esc(href)}" target="_blank" rel="noopener">Download</a>
  </p>
  {viewer}
</section>
"""


def _build_completed_job_report(
    job_id: str,
    status: dict,
    stages: list[dict] | None = None,
    *,
    pdf_path: str | None = None,
) -> str:
    """Render scores already computed by Document MCP (confidence.py). UI does not score."""
    conf = status.get("confidence") or {}
    acc = status.get("accuracy_report") if isinstance(status.get("accuracy_report"), dict) else {}
    pct = status.get("scores_pct") or conf.get("scores_pct") or acc.get("scores_pct") or {}
    validation = status.get("validation") if isinstance(status.get("validation"), dict) else {}
    if not validation and isinstance(acc.get("validation"), dict):
        validation = acc["validation"]

    def _p(key: str, *, strong: bool = False) -> str:
        return _score_badge(_as_score_pct(pct.get(key)), strong=strong)

    def _esc(value: object) -> str:
        return _html_esc(value)

    def _table(title: str, headers: list[str], rows: list[list[str]]) -> str:
        head = "".join(
            f'<th style="padding:0.4rem 0.55rem;text-align:left;border-bottom:1px solid #3a3a3a">'
            f"{_esc(h)}</th>"
            for h in headers
        )
        body_rows = []
        for i, row in enumerate(rows):
            border = "border-bottom:1px solid #2a2a2a" if i < len(rows) - 1 else ""
            cells = "".join(
                f'<td style="padding:0.4rem 0.55rem;vertical-align:top;{border}">{c}</td>'
                for c in row
            )
            body_rows.append(f"<tr>{cells}</tr>")
        return f"""
<section style="margin:0 0 1rem 0">
  <h4 style="margin:0 0 0.4rem 0">{_esc(title)}</h4>
  <div style="overflow:auto;max-width:100%">
  <table style="width:100%;border-collapse:collapse;font-size:0.92rem">
    <thead><tr>{head}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
  </div>
</section>
"""

    mapper_llm = _esc(status.get("mapper_llm") or conf.get("mapper_llm") or "")
    validator_llm = _esc(status.get("validator_llm") or conf.get("validator_llm") or "")
    mapper_ok = bool(mapper_llm and mapper_llm != "-")
    validator_ok = bool(validator_llm and validator_llm != "-")
    elapsed = _overall_time_label(status) or "n/a"
    elapsed_banner = ""
    if elapsed != "n/a":
        elapsed_banner = f"""
<div style="margin:0 0 1rem 0;padding:0.75rem 0.9rem;border:1px solid #3a3a3a;border-radius:8px;background:#1a1a1a">
  <div style="opacity:0.8;font-size:0.85rem">Overall time taken</div>
  <div style="font-size:1.35rem;font-weight:700;color:#9EF0B8;margin-top:0.15rem">{_esc(elapsed)}</div>
</div>
"""

    def _avail(ok: bool) -> str:
        color = "#9EF0B8" if ok else "#FF9A9A"
        label = "available" if ok else "NOT available"
        return (
            f'<span style="display:inline-flex;align-items:center;gap:0.4rem">'
            f'<span style="width:0.55rem;height:0.55rem;border-radius:50%;'
            f'background:{color};display:inline-block"></span>'
            f'<span style="color:{color}">{label}</span></span>'
        )

    warning = ""
    if validation.get("passed") is False or status.get("error_message"):
        warning = _error_banner(
            "Completed with errors",
            _job_error_messages(status) or ["Judge or pipeline reported a problem"],
        )

    job_rows = [
        ["Job ID", f"<code>{_esc(job_id)}</code>"],
        ["MCP", _esc(status.get("mcp") or acc.get("mcp") or "document_process_mcp")],
        ["xid", f"<code>{_esc(status.get('xid') or '')}</code>"],
        ["Status", "<strong>completed</strong>"],
        ["Overall time taken", f"<strong>{_esc(elapsed)}</strong>"],
        ["Mapper LLM", f"<code>{mapper_llm or '-'}</code>"],
        ["Validator LLM", f"<code>{validator_llm or '-'}</code>"],
    ]
    job_rows.extend(_unmarked_template_report_rows(status))
    sections = [
        warning,
        elapsed_banner,
        _accuracy_pdf_panel(job_id, pdf_path),
        _table(
            "Job",
            ["Field", "Value"],
            job_rows,
        ),
        _stages_table_html(stages or []),
        _table(
            "LLMs",
            ["Role", "Status"],
            [
                ["LLM #1 (mapper)", _avail(mapper_ok)],
                ["LLM #2 (validator)", _avail(validator_ok)],
            ],
        ),
        _table(
            "Scores (all in %)",
            ["Metric", "Score"],
            [
                ["<strong>Overall confidence</strong>", _p("overall_confidence_pct", strong=True)],
                ["Extraction confidence", _p("extraction_confidence_pct")],
                [
                    "Extraction placeholder detection",
                    _p("extraction_placeholder_detection_pct"),
                ],
                ["Extraction structure", _p("extraction_structure_pct")],
                [
                    "Placeholder mapping (LLM #1)",
                    _p("placeholder_mapping_confidence_pct"),
                ],
                ["Placeholder coverage", _p("placeholder_coverage_pct")],
                ["Table mapping (LLM #1)", _p("table_mapping_confidence_pct")],
                ["Generation integrity", _p("generation_integrity_pct")],
                ["Generation confidence", _p("generation_confidence_pct")],
                [
                    "<strong>Document validation (LLM #2)</strong>",
                    _p("validation_score_pct", strong=True),
                ],
            ],
        ),
    ]
    sections.insert(
        6,
        """
<p style="margin:0 0 0.75rem 0;font-size:0.88rem;opacity:0.9">
  Score colors:
  <span style="color:#fecaca">red &lt; 80%</span>
  · amber 80–89.9%
  · <span style="color:#bbf7d0">green ≥ 90%</span>
</p>
""",
    )

    if validation:
        sections.append(
            _table(
                "Validation detail (LLM #2)",
                ["Field", "Value"],
                [
                    ["Passed", f"<code>{_esc(validation.get('passed'))}</code>"],
                    [
                        "Score",
                        _p("validation_score_pct"),
                    ],
                    ["Summary", _esc(validation.get("summary") or "-")],
                ],
            )
        )
        issues = validation.get("issues") or []
        if issues:
            issue_rows = [
                [
                    _esc(issue.get("severity") or "-"),
                    f"<code>{_esc(issue.get('field') or '')}</code>",
                    _esc(issue.get("message") or ""),
                ]
                for issue in issues
                if isinstance(issue, dict)
            ]
            sections.append(
                _table(
                    "Validation issues (LLM #2)",
                    ["Severity", "Field", "Message"],
                    issue_rows,
                )
            )

    extraction = (
        status.get("extraction_validation")
        if isinstance(status.get("extraction_validation"), dict)
        else None
    )
    if extraction is None and isinstance(acc.get("extraction_validation"), dict):
        extraction = acc.get("extraction_validation")
    if extraction:
        missed = extraction.get("missed_placeholder_suspects") or []
        missed_txt = ", ".join(str(x) for x in missed) if missed else "-"
        sections.append(
            _table(
                "Extraction critic",
                ["Field", "Value"],
                [
                    ["Passed", f"<code>{_esc(extraction.get('passed'))}</code>"],
                    ["Summary", _esc(extraction.get("summary") or "-")],
                    ["Missed placeholders", _esc(missed_txt)],
                ],
            )
        )

    per_ph = pct.get("per_placeholder") or []
    if per_ph:
        ph_rows = [
            [
                f"<code>{_esc(item.get('placeholder'))}</code>",
                f"<code>{_esc(item.get('json_path'))}</code>",
                _score_badge(_item_score_pct(item) if isinstance(item, dict) else None),
                _esc(item.get("rationale") or ""),
            ]
            for item in per_ph
            if isinstance(item, dict)
        ]
        sections.append(
            _table(
                "Placeholder mapping (LLM #1)",
                ["Placeholder", "JSON path", "Score", "Rationale"],
                ph_rows,
            )
        )

    per_col = pct.get("per_table_column") or []
    if per_col:
        col_rows = [
            [
                _esc(item.get("table_index") if item.get("table_index") is not None else ""),
                f"<code>{_esc(item.get('header'))}</code>",
                f"<code>{_esc(item.get('json_field'))}</code>",
                _score_badge(_item_score_pct(item) if isinstance(item, dict) else None),
                f"<code>{_esc(item.get('array_json_path') or '')}</code>",
            ]
            for item in per_col
            if isinstance(item, dict)
        ]
        sections.append(
            _table(
                "Table column mapping (LLM #1)",
                ["Tbl", "Header", "JSON field", "Score", "Array path"],
                col_rows,
            )
        )

    notes = acc.get("notes") or status.get("notes") or conf.get("notes")
    if notes:
        sections.append(
            _table(
                "Notes",
                ["Field", "Value"],
                [["Notes", _esc(notes)]],
            )
        )

    sections.append(
        _table(
            "Trace",
            ["Field", "Value"],
            [
                ["xid", f"<code>{_esc(status.get('xid') or '')}</code>"],
            ],
        )
    )

    return (
        '<div style="font-size:0.95rem;line-height:1.4">'
        + "".join(sections)
        + "</div>"
    ).replace("${", "$&#123;").replace("{{", "{&#123;")


def ui_library_template_dropdown():
    """Choices from GET /documents/templates (Blob + catalog)."""
    try:
        payload = list_library_templates(folder_name=LIBRARY_TEMPLATE_FOLDER)
        names = [
            str(item.get("template_name"))
            for item in payload.get("templates") or []
            if item.get("template_name")
        ]
    except ApiError as exc:
        logger.warning("Library template list failed: %s", exc)
        names = []
    choices = [LIBRARY_PLACEHOLDER, *names]
    return gr.update(choices=choices, value=LIBRARY_PLACEHOLDER)


def ui_generate_document(
    template_source: str,
    library_template: str,
    template_file: object | None,
    json_file: object | None,
    json_text: str,
    skip_validation: bool,
    optimized_flow: bool,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
):
    """Generator: live WebSocket stages, then final report + download path."""
    from ui_app.flow_debug import flow_breakpoint

    flow_breakpoint("ui_generate_document", template_file=template_file, session_id=session_id)

    def _err(msg: str):
        yield _error_banner("Error", msg), None, None, session_id

    # Immediate feedback so the UI is never blank while validating/uploading.
    yield _loading_html("Checking API and preparing upload…"), None, None, session_id

    try:
        health = check_health()
        if not health.get("mapper_available"):
            yield from _err(
                "Mapper LLM is NOT available — document generation requires LLM #1 "
                "(rules fallback is disabled).\n\n"
                f"Configured: {health.get('mapper_provider')}/{health.get('mapper_model')}\n\n"
                "Fix credentials in .env, restart the API, then Refresh API status."
            )
            return
    except ApiError as exc:
        yield from _err(f"Cannot reach API: {exc}")
        return

    source = (template_source or "library").strip().lower()
    use_upload = source.startswith("upload")
    library_name = (library_template or "").strip()
    if library_name == LIBRARY_PLACEHOLDER:
        library_name = ""

    template_path = None
    if use_upload:
        template_path = _resolve_gradio_path(template_file)
        if not template_path:
            yield from _err("Upload a Word .docx template, or switch to a library template.")
            return
        if not template_path.lower().endswith(".docx"):
            yield from _err("Template must be a .docx file.")
            return
    elif not library_name:
        yield from _err(
            f"Select a template from {LIBRARY_TEMPLATE_FOLDER}, or choose Upload and pick a .docx."
        )
        return

    try:
        data = _resolve_json_payload(json_file, json_text)
    except json.JSONDecodeError as exc:
        yield from _err(f"Invalid JSON: {exc}")
        return
    except ValueError as exc:
        yield from _err(str(exc))
        return

    yield _loading_html("Starting document job…"), None, None, session_id

    try:
        if use_upload:
            accepted = create_document_job(
                template_path,
                data,
                skip_validation=skip_validation,
                optimized_flow=bool(optimized_flow),
                session_id=session_id,
                user_id=user_id,
                user_email=user_email,
            )
        else:
            accepted = create_document_job(
                None,
                data,
                folder_name=LIBRARY_TEMPLATE_FOLDER,
                template_name=library_name,
                skip_validation=skip_validation,
                optimized_flow=bool(optimized_flow),
                session_id=session_id,
                user_id=user_id,
                user_email=user_email,
            )
        job_id = accepted["job_id"]
        sid = accepted.get("session_id") or session_id
        ws_url = accepted.get("ws_url")
        stages: list[dict] = []
        yield _progress_html(job_id, stages), None, None, sid

        from ui_app.ui.api_client import (
            get_job_status,
            iter_job_progress,
        )

        try:
            for event in iter_job_progress(job_id, timeout=180.0, ws_url=ws_url):
                stages = _append_ws_stage(stages, event)
                yield _progress_html(job_id, stages), None, None, sid
                if event.get("terminal") or event.get("stage") in {"completed", "failed"}:
                    break
            status = get_job_status(job_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Job WebSocket failed, falling back to long-poll: %s", exc)
            yield _loading_html(
                "WebSocket unavailable — waiting with long-poll (still working)…"
            ), None, None, sid
            status = wait_for_job(job_id, timeout=180.0, ws_url=ws_url)
            for event in status.get("stages") or []:
                stages = _append_ws_stage(stages, event)
            yield _progress_html(job_id, stages), None, None, sid
    except ApiError as exc:
        yield from _err(f"API error: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        yield from _err(f"Error: {exc}")
        return

    if status.get("status") != "completed":
        yield _build_failed_job_report(job_id, status, stages), None, None, sid
        return

    yield _progress_html(job_id, stages, working=True), None, None, sid
    yield _loading_html("Downloading generated document…"), None, None, sid

    out_name = Path(status.get("output_path") or "").name
    if not out_name.endswith(".docx"):
        out_name = f"{job_id}.docx"
    tmp = Path(tempfile.gettempdir()) / out_name
    try:
        download_job_output(job_id, tmp)
    except ApiError as exc:
        yield from _err(f"Generated but download failed: {exc}")
        return

    pdf_path = None
    try:
        pdf_tmp = Path(tempfile.gettempdir()) / f"{job_id}.pdf"
        download_accuracy_pdf(job_id, pdf_tmp)
        pdf_path = str(pdf_tmp)
    except ApiError as exc:
        logger.warning("Accuracy PDF download failed for %s: %s", job_id, exc)

    try:
        status = get_job_status(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not refresh job status %s after download: %s", job_id, exc)
    yield _build_completed_job_report(job_id, status, stages, pdf_path=pdf_path), str(tmp), pdf_path, sid



def ui_health() -> str:
    api_url = get_api_base_url()
    try:
        health = check_health()
    except Exception as exc:  # noqa: BLE001 — API down / network
        return (
            _error_banner("API unreachable", str(exc))
            + f"<p>Tried <code>{_html_esc(api_url)}</code></p>"
            + "<p>Start the backend, or switch hosts in the <b>API targets</b> tab.</p>"
            + "<pre>python run_all_components.py</pre>"
        )

    def _signal(ok: bool) -> str:
        if ok:
            return (
                '<span style="display:inline-flex;align-items:center;gap:0.4rem">'
                '<span style="width:0.65rem;height:0.65rem;border-radius:50%;'
                "background:#9EF0B8;box-shadow:0 0 8px #9EF0B888;"
                'display:inline-block"></span>'
                '<span style="color:#B8F5D0">available</span></span>'
            )
        return (
            '<span style="display:inline-flex;align-items:center;gap:0.4rem">'
            '<span style="width:0.65rem;height:0.65rem;border-radius:50%;'
            "background:#FF9A9A;box-shadow:0 0 8px #FF9A9A66;"
            'display:inline-block"></span>'
            '<span style="color:#FFC4C4">NOT available</span></span>'
        )

    mapper_ok = bool(health.get("mapper_available"))
    validator_ok = bool(health.get("validator_available"))
    speech_ok = bool(health.get("speech_available"))
    doc_mcp_ok = bool(health.get("document_mcp_available"))
    voice_mcp_ok = bool(health.get("voice_mcp_available"))
    maf_ok = bool(health.get("maf_available"))
    maf_mode = health.get("maf_mode") or "-"
    maf_base = health.get("maf_base_url") or ""

    # Prefer live /api/ask/health when v1 health omitted maf (older API)
    if "maf_available" not in health:
        try:
            maf_payload = check_maf_health()
            maf_ok = bool(maf_payload.get("ok"))
            maf_mode = maf_payload.get("mode") or maf_mode
            maf_base = maf_payload.get("maf_base_url") or maf_base
        except Exception:  # noqa: BLE001
            maf_ok = False

    # Live MCP tool catalogue (what MAF can call)
    tool_rows_html = ""
    try:
        tools_payload = list_maf_mcp_tools()
        servers = tools_payload.get("servers")
        if servers:
            iterable = [
                (
                    spec.get("mcp") or spec.get("name"),
                    spec.get("mcp") or spec.get("name"),
                    spec.get("prefix") or spec.get("name"),
                    spec,
                )
                for spec in servers
                if isinstance(spec, dict)
            ]
        else:
            iterable = [
                ("contract_autocreation_mcp", "contract_autocreation_mcp", "document", tools_payload.get("contract_autocreation_mcp") or tools_payload.get("document_process_mcp") or {}),
                ("voice_process_mcp", "voice_process_mcp", "voice", tools_payload.get("voice_process_mcp") or {}),
            ]
        for _key, label, prefix, block in iterable:
            names = block.get("maf_prefixed") or [
                f"{prefix}_{n}" for n in (block.get("tools") or [])
            ]
            available = bool(block.get("available"))
            if names:
                chips = " ".join(
                    f'<code style="margin:0.15rem 0.25rem 0.15rem 0;padding:0.15rem 0.4rem;'
                    f'background:#1e1e1e;border-radius:4px;font-size:0.85rem">'
                    f"{_html_esc(n)}</code>"
                    for n in names
                )
            elif block.get("error"):
                chips = (
                    f'<span style="color:#FFC4C4">unreachable — '
                    f"{_html_esc(block.get('error'))}</span>"
                )
            else:
                chips = '<span style="opacity:0.7">no tools reported</span>'
            tool_rows_html += (
                f'<tr style="border-bottom:1px solid #2a2a2a">'
                f'<td style="padding:0.4rem 0.6rem;vertical-align:top">'
                f"<strong>{_html_esc(label)}</strong><br>"
                f'<span style="opacity:0.75;font-size:0.85rem">{_signal(available)}</span>'
                f"</td>"
                f'<td style="padding:0.4rem 0.6rem;line-height:1.8">{chips}</td>'
                f"</tr>"
            )
    except Exception as exc:  # noqa: BLE001
        tool_rows_html = (
            f'<tr><td colspan="2" style="padding:0.45rem 0.6rem;color:#FFC4C4">'
            f"Could not load MCP tools: {_html_esc(exc)}"
            f"</td></tr>"
        )

    warn = ""
    if not mapper_ok:
        warn = (
            "<p style='color:#FFD0A8'><strong>Document generate is blocked until "
            "mapper LLM is available.</strong> Check credentials in "
            "<code>.env</code> and restart the API.</p>"
        )
    if not maf_ok:
        warn += (
            "<p style='color:#FFD0A8'><strong>Central agent (MAF) is not available.</strong> "
            "Start it with <code>python run_all_components.py</code> "
            "(or <code>--maf-only</code>), or run <code>./run.sh</code> in "
            "<code>central-agentic-flow</code>.</p>"
        )

    maf_meta = f"mode <code>{_html_esc(maf_mode)}</code>"
    if maf_base:
        maf_meta += f" · <code>{_html_esc(maf_base)}</code>"
    maf_meta += f" · ask <code>{_html_esc(api_url)}/api/ask</code>"

    if maf_ok:
        maf_banner = (
            '<div style="padding:0.75rem 1rem;margin:0.5rem 0 0.85rem 0;'
            "border:1px solid #2a6b45;border-radius:8px;background:#13261c\">"
            '<div style="font-size:1.05rem;letter-spacing:0.02em">'
            '<strong style="color:#B8F5D0">MAF CENTRAL AGENT AVAILABLE</strong>'
            f" {_signal(True)}</div>"
            f'<div style="opacity:0.85;margin-top:0.35rem;font-size:0.9rem">{maf_meta}</div>'
            '<div style="margin-top:0.75rem">'
            "<strong>Available MCP tools</strong>"
            '<table style="width:100%;border-collapse:collapse;margin-top:0.4rem">'
            "<thead><tr style='text-align:left;border-bottom:1px solid #3a3a3a'>"
            "<th style='padding:0.3rem 0.6rem'>MCP server</th>"
            "<th style='padding:0.3rem 0.6rem'>Tools (MAF names)</th>"
            "</tr></thead>"
            f"<tbody>{tool_rows_html}</tbody></table></div></div>"
        )
    else:
        maf_banner = (
            '<div style="padding:0.75rem 1rem;margin:0.5rem 0 0.85rem 0;'
            "border:1px solid #6b2a2a;border-radius:8px;background:#261313\">"
            '<div style="font-size:1.05rem">'
            '<strong style="color:#FFC4C4">MAF CENTRAL AGENT NOT AVAILABLE</strong>'
            f" {_signal(False)}</div>"
            f'<div style="opacity:0.85;margin-top:0.35rem;font-size:0.9rem">{maf_meta}</div>'
            '<div style="margin-top:0.75rem;opacity:0.9">'
            "<strong>Available MCP tools</strong> (still listed when MCP servers are up)"
            '<table style="width:100%;border-collapse:collapse;margin-top:0.4rem">'
            "<thead><tr style='text-align:left;border-bottom:1px solid #3a3a3a'>"
            "<th style='padding:0.3rem 0.6rem'>MCP server</th>"
            "<th style='padding:0.3rem 0.6rem'>Tools (MAF names)</th>"
            "</tr></thead>"
            f"<tbody>{tool_rows_html}</tbody></table></div></div>"
        )

    return f"""
<div style="font-size:0.95rem;line-height:1.45">
  <p><strong>API:</strong> <code>{api_url}</code>
     · status <code>{health.get('status', 'ok')}</code></p>
  {maf_banner}

  <table style="width:100%;border-collapse:collapse;margin:0.4rem 0 0.9rem 0">
    <thead>
      <tr style="text-align:left;border-bottom:1px solid #3a3a3a">
        <th style="padding:0.35rem 0.6rem">Service</th>
        <th style="padding:0.35rem 0.6rem">Status</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom:1px solid #2a2a2a">
        <td style="padding:0.45rem 0.6rem"><strong>Speech</strong></td>
        <td style="padding:0.45rem 0.6rem">{_signal(speech_ok)}</td>
      </tr>
      <tr style="border-bottom:1px solid #2a2a2a">
        <td style="padding:0.45rem 0.6rem"><strong>LLM #1 Mapper</strong></td>
        <td style="padding:0.45rem 0.6rem">{_signal(mapper_ok)}</td>
      </tr>
      <tr style="border-bottom:1px solid #2a2a2a">
        <td style="padding:0.45rem 0.6rem"><strong>LLM #2 Validator</strong></td>
        <td style="padding:0.45rem 0.6rem">{_signal(validator_ok)}</td>
      </tr>
      <tr style="border-bottom:1px solid #2a2a2a">
        <td style="padding:0.45rem 0.6rem"><strong>contract_autocreation_mcp</strong></td>
        <td style="padding:0.45rem 0.6rem">{_signal(doc_mcp_ok)}</td>
      </tr>
      <tr>
        <td style="padding:0.45rem 0.6rem"><strong>voice_process_mcp</strong></td>
        <td style="padding:0.45rem 0.6rem">{_signal(voice_mcp_ok)}</td>
      </tr>
    </tbody>
  </table>
  {warn}
</div>
"""


def ui_central_agent_ask(
    message: str,
    history: list | None,
    session_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    role: str | None = None,
):
    """Chat turn against the MAF central orchestrator (via API /api/ask)."""
    from ui_app.flow_debug import flow_breakpoint

    flow_breakpoint("ui_central_agent_ask", message=message, session_id=session_id)
    history = list(history or [])
    text = (message or "").strip()
    sid = (session_id or "").strip() or None
    who = (role or "").strip() or None
    if not text:
        return history, "", sid

    history = history + [{"role": "user", "content": text}]
    try:
        result = ask_central_agent(
            text,
            session_id=sid,
            user_id=(user_id or "").strip() or None,
            user_email=(user_email or "").strip() or None,
            persona=who,
        )
        sid = result.get("session_id") or sid
        reply = (result.get("text") or "").strip() or "(empty MAF response)"
        rid = result.get("response_id")
        extra = []
        if rid:
            extra.append(f"_response_id: `{rid}`_")
        if sid:
            extra.append(f"_session_id: `{sid}`_")
        used_role = result.get("persona") or result.get("role")
        used_version = result.get("version")
        validation = result.get("validation") or {}
        if used_role:
            extra.append(f"_persona: `{used_role}`_")
        if used_version:
            extra.append(f"_version: `{used_version}`_")
        classification = validation.get("classification")
        if classification:
            extra.append(f"_validation: `{classification}`_")
        if result.get("authorized") is False:
            extra.append("_authorized: `false`_")
        if extra:
            reply = f"{reply}\n\n" + " · ".join(extra)
    except ApiError as exc:
        reply = f"**Central agent error:** {exc}"
    except Exception as exc:  # noqa: BLE001
        reply = f"**Error:** {exc}"

    history = history + [{"role": "assistant", "content": reply}]
    return history, "", sid


def _pretty_json(value: object, *, limit: int = 4000) -> str:
    if value is None:
        return "-"
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        text = str(value)
    if len(text) > limit:
        return text[: limit - 20] + f"\n...<truncated:{len(text)}>"
    return text


def ui_recent_jobs_for_trace(limit: float | int = 15) -> str:
    """Show recent jobs with xid so the user can copy one into the lookup box."""
    try:
        payload = list_document_jobs(limit=int(limit))
        jobs = payload.get("jobs") or []
    except Exception as exc:  # noqa: BLE001
        return f'<div style="color:#FFC4C4">Failed to list jobs: {_html_esc(exc)}</div>'

    if not jobs:
        return "<p>No document jobs yet. Generate a document first.</p>"

    rows = []
    for job in jobs:
        xid = job.get("xid") or ""
        failed = job.get("status") == "failed"
        err = (job.get("error_message") or "").strip()
        err_cell = _html_esc(err[:160] + ("…" if len(err) > 160 else "")) if err else "—"
        rows.append(
            "<tr>"
            f"<td style='padding:0.35rem 0.5rem'><code>{_html_esc(job.get('job_id'))}</code></td>"
            f"<td style='padding:0.35rem 0.5rem'><code>{_html_esc(xid)}</code></td>"
            f"<td style='padding:0.35rem 0.5rem;color:{'#FF9A9A' if failed else 'inherit'}'>"
            f"{_html_esc(job.get('status'))}</td>"
            f"<td style='padding:0.35rem 0.5rem;color:#FFC4C4'>{err_cell}</td>"
            f"<td style='padding:0.35rem 0.5rem'>{_html_esc(_overall_time_label(job) or '—')}</td>"
            f"<td style='padding:0.35rem 0.5rem'>{_html_esc(job.get('created_at'))}</td>"
            "</tr>"
        )
    return f"""
<div style="font-size:0.92rem">
  <h4 style="margin:0 0 0.4rem 0">Recent jobs (copy xid)</h4>
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="text-align:left;border-bottom:1px solid #3a3a3a">
        <th style="padding:0.35rem 0.5rem">Job ID</th>
        <th style="padding:0.35rem 0.5rem">xid</th>
        <th style="padding:0.35rem 0.5rem">Status</th>
        <th style="padding:0.35rem 0.5rem">Error</th>
        <th style="padding:0.35rem 0.5rem">Overall time</th>
        <th style="padding:0.35rem 0.5rem">Created</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def ui_lookup_trace(xid: str) -> str:
    """Render HTTP / tool / LLM call logs for one xid as segregated tables."""
    corr = (xid or "").strip()
    if not corr:
        return '<div style="color:#FFC4C4">Enter an xid to look up logs.</div>'

    try:
        payload = get_trace_by_xid(corr)
    except Exception as exc:  # noqa: BLE001
        return f'<div style="color:#FFC4C4">Trace lookup failed: {_html_esc(exc)}</div>'

    jobs = payload.get("jobs") or []
    logs = payload.get("logs") or []

    job_rows = []
    for job in jobs:
        job_rows.append(
            "<tr>"
            f"<td style='padding:0.35rem 0.5rem'><code>{_html_esc(job.get('job_id'))}</code></td>"
            f"<td style='padding:0.35rem 0.5rem'>{_html_esc(job.get('status'))}</td>"
            f"<td style='padding:0.35rem 0.5rem'>{_html_esc(job.get('completed_at') or job.get('created_at'))}</td>"
            "</tr>"
        )
    if not job_rows:
        job_rows.append(
            "<tr><td colspan='3' style='padding:0.4rem 0.5rem;opacity:0.75'>"
            "No document jobs linked to this xid.</td></tr>"
        )

    log_rows = []
    for i, log in enumerate(logs):
        status = str(log.get("status") or "")
        status_color = "#9EF0B8" if status == "ok" else "#FF9A9A"
        req = _pretty_json(log.get("request"), limit=2500)
        resp = _pretty_json(log.get("response"), limit=2500)
        err = log.get("error_message") or ""
        latency = log.get("latency_ms")
        latency_s = f"{float(latency):.0f} ms" if isinstance(latency, (int, float)) else "-"
        border = "border-bottom:1px solid #2a2a2a" if i < len(logs) - 1 else ""
        log_rows.append(
            f"""
<tr>
  <td style="padding:0.4rem 0.5rem;vertical-align:top;{border}">
    <code>{_html_esc(log.get('kind'))}</code>
  </td>
  <td style="padding:0.4rem 0.5rem;vertical-align:top;{border}">
    <strong>{_html_esc(log.get('name'))}</strong>
  </td>
  <td style="padding:0.4rem 0.5rem;vertical-align:top;{border}">
    <span style="color:{status_color}">{_html_esc(status)}</span>
  </td>
  <td style="padding:0.4rem 0.5rem;vertical-align:top;{border}">{_html_esc(latency_s)}</td>
  <td style="padding:0.4rem 0.5rem;vertical-align:top;{border}">
    {_html_esc(log.get('created_at'))}
  </td>
</tr>
<tr>
  <td colspan="5" style="padding:0 0.5rem 0.75rem 0.5rem;{border}">
    <details>
      <summary style="cursor:pointer;opacity:0.85">Request / response</summary>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.6rem;margin-top:0.4rem">
        <pre style="white-space:pre-wrap;background:#1a1a1a;padding:0.5rem;border-radius:4px;font-size:0.8rem">{_html_esc(req)}</pre>
        <pre style="white-space:pre-wrap;background:#1a1a1a;padding:0.5rem;border-radius:4px;font-size:0.8rem">{_html_esc(resp)}</pre>
      </div>
      {"<p style='color:#FFC4C4'><strong>Error:</strong> " + _html_esc(err) + "</p>" if err else ""}
    </details>
  </td>
</tr>
"""
        )
    if not logs:
        log_rows.append(
            "<tr><td colspan='5' style='padding:0.5rem;opacity:0.75'>"
            "No call logs for this xid yet.</td></tr>"
        )

    return f"""
<div style="font-size:0.93rem;line-height:1.4">
  <h3 style="margin:0 0 0.5rem 0">Trace for xid <code>{_html_esc(corr)}</code></h3>
  <p style="opacity:0.8;margin:0 0 0.8rem 0">
    {int(payload.get('job_count') or 0)} job(s) · {int(payload.get('log_count') or 0)} log(s)
  </p>

  <h4 style="margin:0.6rem 0 0.35rem 0">Linked jobs</h4>
  <table style="width:100%;border-collapse:collapse;margin-bottom:1rem">
    <thead>
      <tr style="text-align:left;border-bottom:1px solid #3a3a3a">
        <th style="padding:0.35rem 0.5rem">Job ID</th>
        <th style="padding:0.35rem 0.5rem">Status</th>
        <th style="padding:0.35rem 0.5rem">Time</th>
      </tr>
    </thead>
    <tbody>{''.join(job_rows)}</tbody>
  </table>

  <h4 style="margin:0.6rem 0 0.35rem 0">Call logs (HTTP / tools / LLM / speech / MCP)</h4>
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="text-align:left;border-bottom:1px solid #3a3a3a">
        <th style="padding:0.35rem 0.5rem">Kind</th>
        <th style="padding:0.35rem 0.5rem">Name</th>
        <th style="padding:0.35rem 0.5rem">Status</th>
        <th style="padding:0.35rem 0.5rem">Latency</th>
        <th style="padding:0.35rem 0.5rem">Created</th>
      </tr>
    </thead>
    <tbody>{''.join(log_rows)}</tbody>
  </table>
</div>
"""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Document Processing Agentic Flow") as demo:
        gr.Markdown(
            "# Document Processing Agentic Flow\n"
            "Generate Word docs · Voice contracts · **Central agent (MAF)** orchestrates both MCPs"
        )
        api_caption = gr.Markdown(value=ui_api_target_caption())

        with gr.Row():
            health_box = gr.HTML(value=ui_health())

        with gr.Row():
            session_id_box = gr.Textbox(
                label="Session ID (auto-created on first request; reused after)",
                interactive=True,
                scale=3,
            )
            user_id_box = gr.Textbox(
                label="User ID",
                placeholder="optional-user-id",
                scale=1,
            )
            user_email_box = gr.Textbox(
                label="User email",
                placeholder="optional@example.com",
                scale=2,
            )
            new_session_btn = gr.Button("New session", scale=1)

        def _clear_session():
            return ""

        new_session_btn.click(fn=_clear_session, outputs=[session_id_box])

        # ------------------------------------------------------------------ Central agent / MAF
        with gr.Tab("Central Agent (MAF)"):
            gr.Markdown(
                "### Central agent system (Microsoft Agent Framework)\n"
                "Status banner above shows **MAF CENTRAL AGENT AVAILABLE** and the "
                "**Available MCP tools** catalogue.\n\n"
                "Natural-language asks go to **MAF** via "
                f"`{get_api_base_url()}/api/ask`, which orchestrates "
                "**document-processing-mcp** and **voice_enable_mcp** tools.\n\n"
                "Each ask creates/reuses a **session_id** (SQLite) and returns it here.\n\n"
                "Paste **Persona** as the definition (scope and prohibitions). "
                "Type the question as **Prompt**. An LLM validator runs first; "
                "if confidence is below the configured floor (default 95%), "
                "the assistant does not run.\n\n"
                "**Example Prompt:** `how many contracts going to expire in the next quarter`"
            )
            maf_chat = gr.Chatbot(label="Central agent chat", height=420)
            with gr.Row():
                maf_role = gr.Textbox(
                    label="Persona",
                    placeholder="Paste the persona definition (responsibilities, prohibitions, ...)",
                    lines=5,
                    scale=1,
                )
            with gr.Row():
                maf_input = gr.Textbox(
                    label="Prompt",
                    placeholder="how many contracts going to expire in the next quarter",
                    scale=4,
                )
                maf_send = gr.Button("Ask", variant="primary", scale=1)

            maf_send.click(
                fn=ui_central_agent_ask,
                inputs=[
                    maf_input,
                    maf_chat,
                    session_id_box,
                    user_id_box,
                    user_email_box,
                    maf_role,
                ],
                outputs=[maf_chat, maf_input, session_id_box],
            )
            maf_input.submit(
                fn=ui_central_agent_ask,
                inputs=[
                    maf_input,
                    maf_chat,
                    session_id_box,
                    user_id_box,
                    user_email_box,
                    maf_role,
                ],
                outputs=[maf_chat, maf_input, session_id_box],
            )

        # ------------------------------------------------------------------ Document (1st)
        with gr.Tab("Generate Document"):
            gr.Markdown(
                f"Pick a template from Blob folder **`{LIBRARY_TEMPLATE_FOLDER}`**, "
                "or **upload** a `.docx`. JSON is sent in the request "
                "(paste below, or load a local `.json`). "
                f"Job: `{get_api_base_url()}/api/v1/documents/jobs`."
            )
            with gr.Row():
                with gr.Column():
                    template_source = gr.Radio(
                        choices=["library", "upload"],
                        value="library",
                        label="Template source",
                        info=f"library = {LIBRARY_TEMPLATE_FOLDER} on Blob (or local templates dir)",
                    )
                    with gr.Row():
                        library_dropdown = gr.Dropdown(
                            label=f"Library templates ({LIBRARY_TEMPLATE_FOLDER})",
                            choices=[LIBRARY_PLACEHOLDER],
                            value=LIBRARY_PLACEHOLDER,
                            interactive=True,
                        )
                        refresh_library_btn = gr.Button("Refresh list")
                    template_upload = gr.File(
                        label="Upload Word template (.docx)",
                        file_types=[".docx"],
                        file_count="single",
                        type="filepath",
                    )
                    json_input = gr.Textbox(
                        label="JSON data (sent in the request)",
                        lines=12,
                        placeholder='{"invoice_number": "INV-001", "customer": {"name": "Acme"}}',
                    )
                    with gr.Accordion("Optional: load JSON from a local file into the request", open=False):
                        json_file_upload = gr.File(
                            label="Local .json (parsed and sent as request JSON, not as a file upload)",
                            file_types=[".json"],
                            file_count="single",
                            type="filepath",
                        )
                    skip_validation = gr.Checkbox(label="Skip LLM #2 validation", value=False)
                    optimized_flow = gr.Checkbox(
                        label="Optimized flow (complexity + cheaper mapper first)",
                        value=False,
                    )
                    generate_btn = gr.Button("Generate document", variant="primary")
                with gr.Column():
                    job_report = gr.HTML(
                        label="Job result",
                        value=(
                            '<div style="opacity:0.75;line-height:1.4">'
                            "Select a library template or upload a .docx, paste JSON, then "
                            "<strong>Generate document</strong>."
                            "A spinner and live stages will appear here. When the job "
                            "finishes, the accuracy report PDF is shown in this panel."
                            "</div>"
                        ),
                    )
                    with gr.Row():
                        output_file = gr.File(
                            label="Download generated .docx",
                            type="filepath",
                            interactive=False,
                        )
                        accuracy_pdf = gr.File(
                            label="Download accuracy report (job_id.pdf)",
                            type="filepath",
                            interactive=False,
                        )

            generate_btn.click(
                fn=ui_generate_document,
                inputs=[
                    template_source,
                    library_dropdown,
                    template_upload,
                    json_file_upload,
                    json_input,
                    skip_validation,
                    optimized_flow,
                    session_id_box,
                    user_id_box,
                    user_email_box,
                ],
                outputs=[job_report, output_file, accuracy_pdf, session_id_box],
                show_progress="full",
            )
            refresh_library_btn.click(
                fn=ui_library_template_dropdown,
                outputs=[library_dropdown],
            )

        # ------------------------------------------------------------------ Voice chat (2nd)
        with gr.Tab("Voice to Contract"):
            gr.Markdown(
                "### Contract assistant (chat)\n"
                "Ask to create a contract. The bot finds the legal entity + matching "
                "contract reference, then waits for your confirmation "
                "(human-in-the-loop). After you confirm, it creates a **dummy text "
                "contract** (and `.docx`).\n\n"
                "**Try this prompt:**\n"
                "`please create contract with legal entity AVC contract reference number CR 1001`\n\n"
                "Then reply: `yes` or `CR-1001`"
            )
            chat_pending = gr.State({})
            with gr.Row():
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        label="Contract chat",
                        height=420,
                    )
                    with gr.Row():
                        chat_input = gr.Textbox(
                            label="Message",
                            placeholder=(
                                "please create contract with legal entity AVC "
                                "contract reference number CR 1001"
                            ),
                            scale=4,
                        )
                        chat_send = gr.Button("Send", variant="primary", scale=1)
                    with gr.Accordion("Optional: speak instead of typing", open=False):
                        audio_input = gr.Audio(
                            label="Record or upload audio",
                            sources=["microphone", "upload"],
                            type="filepath",
                        )
                        language = gr.Textbox(
                            label="Language (optional)",
                            placeholder="en",
                        )
                        provider = gr.Dropdown(
                            label="Speech provider",
                            choices=["auto", "groq", "openai", "azure_openai"],
                            value="auto",
                        )
                        audio_send = gr.Button("Transcribe & send to chat")
                with gr.Column(scale=2):
                    contract_text_file = gr.File(
                        label="Download dummy contract (.txt)",
                        type="filepath",
                        interactive=False,
                    )
                    contract_docx_file = gr.File(
                        label="Download dummy contract (.docx)",
                        type="filepath",
                        interactive=False,
                    )
                    transcript_note = gr.Textbox(
                        label="Last audio transcript",
                        interactive=False,
                    )

            def _chat_submit(message, history, pending, session_id, user_id, user_email):
                new_history, new_pending, txt, docx, sid = ui_contract_chat(
                    message, history, pending, session_id, user_id, user_email
                )
                return new_history, new_pending, "", txt, docx, sid

            chat_send.click(
                fn=_chat_submit,
                inputs=[
                    chat_input,
                    chatbot,
                    chat_pending,
                    session_id_box,
                    user_id_box,
                    user_email_box,
                ],
                outputs=[
                    chatbot,
                    chat_pending,
                    chat_input,
                    contract_text_file,
                    contract_docx_file,
                    session_id_box,
                ],
            )
            chat_input.submit(
                fn=_chat_submit,
                inputs=[
                    chat_input,
                    chatbot,
                    chat_pending,
                    session_id_box,
                    user_id_box,
                    user_email_box,
                ],
                outputs=[
                    chatbot,
                    chat_pending,
                    chat_input,
                    contract_text_file,
                    contract_docx_file,
                    session_id_box,
                ],
            )
            audio_send.click(
                fn=ui_contract_chat_from_audio,
                inputs=[
                    audio_input,
                    chatbot,
                    chat_pending,
                    language,
                    provider,
                    session_id_box,
                    user_id_box,
                    user_email_box,
                ],
                outputs=[
                    chatbot,
                    chat_pending,
                    contract_text_file,
                    contract_docx_file,
                    transcript_note,
                    session_id_box,
                ],
            )

        # ------------------------------------------------------------------ Trace logs by xid
        with gr.Tab("Trace Logs (xid)"):
            gr.Markdown(
                "Look up **HTTP / tool / LLM / speech / MCP** call logs by correlation "
                "`xid` (`X-Request-ID`). Paste an xid from a job result, or pick one "
                "from recent jobs below."
            )
            with gr.Row():
                xid_input = gr.Textbox(
                    label="xid",
                    placeholder="paste xid (e.g. from Job result Persistence table)",
                    scale=4,
                )
                lookup_btn = gr.Button("Lookup logs", variant="primary", scale=1)
            with gr.Row():
                refresh_jobs_btn = gr.Button("Refresh recent jobs", size="sm")
            recent_jobs_box = gr.HTML(value=ui_recent_jobs_for_trace())
            trace_box = gr.HTML(
                value="<p style='opacity:0.75'>Enter an xid and click Lookup logs.</p>"
            )

            lookup_btn.click(fn=ui_lookup_trace, inputs=[xid_input], outputs=[trace_box])
            xid_input.submit(fn=ui_lookup_trace, inputs=[xid_input], outputs=[trace_box])
            refresh_jobs_btn.click(
                fn=ui_recent_jobs_for_trace,
                outputs=[recent_jobs_box],
            )

        with gr.Tab("Admin"):
            gr.Markdown(
                "### Admin API (templates + master data)\n"
                "Calls `/api/v1/admin/*` on the **current API host**. "
                "Put `admin_api_key` in **API targets** JSON (same as `ADMIN_API_KEY` on the API). "
                "503 means the API has no admin key configured."
            )
            with gr.Accordion("Word templates", open=True):
                admin_folder = gr.Textbox(
                    label="folder_name",
                    value="ipp_pricing_default_template",
                    info="Blob path: templates/ipp_pricing_default_template/{name}.docx",
                )
                admin_tpl_name = gr.Textbox(
                    label="template_name (optional; defaults to uploaded filename)",
                )
                admin_tpl_file = gr.File(
                    label="Upload .docx into the library",
                    file_types=[".docx"],
                    file_count="single",
                    type="filepath",
                )
                with gr.Row():
                    admin_upload_btn = gr.Button("Upload template", variant="primary")
                    admin_list_tpl_btn = gr.Button("List templates")
                admin_tpl_out = gr.HTML(value="<p>Click List templates.</p>")
                admin_upload_btn.click(
                    fn=ui_upload_template,
                    inputs=[admin_tpl_file, admin_folder, admin_tpl_name],
                    outputs=[admin_tpl_out],
                )
                admin_list_tpl_btn.click(
                    fn=ui_list_templates,
                    inputs=[admin_folder],
                    outputs=[admin_tpl_out],
                )
            with gr.Accordion("Master data (legal / sales notice blocks)", open=True):
                gr.Markdown(
                    "Fills `<Legal_Department_Master_Data>` and `<Sales_Excellence_Master_Data>` "
                    "in document jobs unless JSON `system_instruction` override is true."
                )
                md_key = gr.Textbox(
                    label="placeholder_key",
                    value="Legal_Department_Master_Data",
                )
                md_cat = gr.Dropdown(
                    label="category",
                    choices=["legal", "sales", "general"],
                    value="legal",
                )
                md_content = gr.Textbox(
                    label="content",
                    lines=6,
                    value=(
                        "Legal Department\n"
                        "200 Connell Drive, Suite 1000\n"
                        "Berkeley Heights, NJ 07922\n"
                        "E-mail: pmo@ABCTec.com"
                    ),
                )
                md_active = gr.Checkbox(label="active", value=True)
                with gr.Row():
                    md_save_btn = gr.Button("Save / replace block", variant="primary")
                    md_list_btn = gr.Button("List blocks")
                    md_del_btn = gr.Button("Delete placeholder_key")
                md_out = gr.HTML(value="<p>Click List blocks.</p>")
                md_save_btn.click(
                    fn=ui_save_master,
                    inputs=[md_key, md_cat, md_content, md_active],
                    outputs=[md_out],
                )
                md_list_btn.click(fn=ui_list_master, outputs=[md_out])
                md_del_btn.click(fn=ui_delete_master, inputs=[md_key], outputs=[md_out])

        with gr.Tab("API targets"):
            gr.Markdown(
                "### JSON config for local vs deployed API\n"
                "Set `active_target` to a key under `targets`. "
                "Replace the Azure hostname, paste `admin_api_key` if you use Admin, "
                "then **Apply and ping**. Saved to `UI/config/ui_runtime.json` (not committed).\n\n"
                "Example file: `UI/config/ui_targets.example.json`."
            )
            api_json = gr.Code(
                label="ui_targets.json",
                language="json",
                value=ui_config_json(),
            )
            apply_api_btn = gr.Button("Apply and ping API", variant="primary")
            apply_api_btn.click(
                fn=ui_apply_api_config,
                inputs=[api_json],
                outputs=[api_json, health_box],
            ).then(fn=ui_api_target_caption, outputs=[api_caption])

        refresh_health = gr.Button("Refresh API status")
        refresh_health.click(fn=ui_health, outputs=[health_box])

        demo.load(fn=ui_library_template_dropdown, outputs=[library_dropdown])

    return demo


def main() -> None:
    from ui_app.flow_debug import install_flow_logger

    install_flow_logger()
    cfg = settings()
    app = build_ui()
    app.launch(
        server_name=cfg.gradio_host,
        server_port=cfg.gradio_port,
        share=False,
    )


if __name__ == "__main__":
    main()
