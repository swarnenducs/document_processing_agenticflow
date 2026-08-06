"""Gradio UI — record voice, send to FastAPI, generate documents."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import gradio as gr

from document_processing_agenticflow.core.settings import settings
from document_processing_agenticflow.ui.api_client import (
    ApiError,
    check_health,
    confirm_voice_contract,
    create_document_job,
    download_job_output,
    get_trace_by_xid,
    list_document_jobs,
    run_voice_contract_audio,
    run_voice_contract_text,
    wait_for_job,
)

# Allow: python -m document_processing_agenticflow.ui.gradio_app


def _resolve_gradio_path(value: object | None) -> str | None:
    """Normalize Gradio File/Audio return values to a local filepath."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
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
    return msg or "Please ask a relevant service."


def _run_contract_request(text: str) -> dict:
    """Prefer API; fall back to in-process workflow if API is down."""
    try:
        return run_voice_contract_text(text, auto_create=False)
    except Exception:
        from document_processing_agenticflow.services.voice_contract_workflow import (
            run_voice_contract_workflow,
        )
        from document_processing_agenticflow.storage.job_store import JobStore

        return run_voice_contract_workflow(text, store=JobStore()).to_dict()


def _confirm_contract_request(
    legal_entity: str,
    contract_reference_number: str,
    *,
    transcript: str | None = None,
    thread_id: str | None = None,
    user_text: str | None = None,
) -> dict:
    try:
        return confirm_voice_contract(
            legal_entity,
            contract_reference_number,
            transcript=transcript,
            thread_id=thread_id,
            user_text=user_text,
        )
    except Exception:
        from document_processing_agenticflow.services.voice_contract_workflow import (
            confirm_voice_contract as local_confirm,
        )
        from document_processing_agenticflow.storage.job_store import JobStore

        store = JobStore()
        result = local_confirm(
            entity_code_or_name=legal_entity,
            contract_reference_number=contract_reference_number,
            store=store,
            transcript=transcript,
            thread_id=thread_id,
            user_text=user_text or "yes",
        )
        payload = result.to_dict()
        if result.ok and result.status == "completed":
            saved = store.save_voice_contract(
                spoken_name=result.spoken_name or "",
                spoken_number=result.spoken_number or "",
                contact=result.contact or result.legal_entity,
                legal_entity=result.legal_entity,
                pricelist=result.pricelist,
                contract_payload=result.contract_payload,
                contract_file=result.contract_file,
                transcript=result.transcript,
            )
            payload["contract_id"] = saved["contract_id"]
            payload["message"] = (
                f"{result.message} Saved to SQLite as contract `{saved['contract_id']}`."
            )
        return payload


def ui_contract_chat(
    message: str,
    history: list[dict[str, str]] | None,
    pending: dict | None,
) -> tuple[list[dict[str, str]], dict | None, str | None, str | None]:
    """Chat-style human-in-the-loop contract creation."""
    history = list(history or [])
    pending = dict(pending or {})
    text = (message or "").strip()
    if not text:
        return history, pending, None, None

    history.append({"role": "user", "content": text})

    try:
        # Confirmation turn
        if pending.get("awaiting_confirmation"):
            from document_processing_agenticflow.services.voice_contract_workflow import (
                format_contract_ref,
                is_confirmation,
            )

            chosen_ref = pending.get("contract_reference_number")
            entity_key = pending.get("legal_entity_code") or pending.get("legal_entity_name")
            ref = chosen_ref if is_confirmation(text) else format_contract_ref(text)
            result = _confirm_contract_request(
                str(entity_key),
                str(ref),
                transcript=pending.get("transcript"),
                thread_id=pending.get("thread_id"),
                user_text=text,
            )
            history.append({"role": "assistant", "content": _assistant_from_result(result)})
            text_file = result.get("contract_text_file")
            docx_file = result.get("contract_file")
            if result.get("ok"):
                return history, {}, text_file, docx_file
            return history, pending, None, None

        # New request turn
        result = _run_contract_request(text)
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
            return history, pending, None, None

        if result.get("ok") and result.get("status") == "completed":
            return history, {}, result.get("contract_text_file"), result.get("contract_file")

        return history, {}, None, None
    except Exception as exc:  # noqa: BLE001
        history.append({"role": "assistant", "content": f"Error: {exc}"})
        return history, pending, None, None


def ui_contract_chat_from_audio(
    audio_path: object | None,
    history: list[dict[str, str]] | None,
    pending: dict | None,
    language: str,
    provider: str,
) -> tuple[list[dict[str, str]], dict | None, str | None, str | None, str]:
    path = _resolve_gradio_path(audio_path)
    if not path:
        history = list(history or [])
        history.append(
            {
                "role": "assistant",
                "content": "Record or upload audio first, or type in the chat box.",
            }
        )
        return history, pending or {}, None, None, ""
    try:
        lang = language.strip() or None
        prov = None if provider in {"", "default", "auto"} else provider
        result = run_voice_contract_audio(path, language=lang, provider=prov)
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
            return history, pending or {}, None, None, ""
        new_history, new_pending, txt, docx = ui_contract_chat(transcript, history, pending)
        return new_history, new_pending, txt, docx, transcript
    except ApiError as exc:
        history = list(history or [])
        # Prefer local transcription fallback on API/speech connection failures.
        try:
            from document_processing_agenticflow.services.speech_to_text import (
                transcribe_audio,
            )

            lang = language.strip() or None
            prov = None if provider in {"", "default", "auto"} else provider
            local = transcribe_audio(path, language=lang, provider=prov)
            transcript = local.text
            new_history, new_pending, txt, docx = ui_contract_chat(
                transcript, history, pending
            )
            return new_history, new_pending, txt, docx, transcript
        except Exception as local_exc:  # noqa: BLE001
            history.append(
                {
                    "role": "assistant",
                    "content": (
                        f"Speech transcription failed (`{exc}` / `{local_exc}`).\n\n"
                        "Please **type** this in the chat box instead:\n"
                        "`please create contract with legal entity AVC contract "
                        "reference number CR 1001`\n"
                        "Then reply `yes`."
                    ),
                }
            )
            return history, pending or {}, None, None, ""
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
        return history, pending or {}, None, None, ""


def _resolve_json_payload(json_file: object | None, json_text: str) -> dict | Path:
    file_path = _resolve_gradio_path(json_file)
    if file_path:
        p = Path(file_path)
        if p.suffix.lower() != ".json":
            raise ValueError("JSON upload must be a `.json` file")
        return p

    if not json_text.strip():
        raise ValueError("Upload a `.json` file or paste JSON data")

    payload = json.loads(json_text)
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object `{}`")
    return payload


def ui_generate_document(
    template_file: object | None,
    json_file: object | None,
    json_text: str,
    skip_validation: bool,
) -> tuple[str, str | None]:
    def _err(msg: str) -> tuple[str, None]:
        safe = (
            str(msg)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        return f'<div style="color:#FFC4C4;line-height:1.45">{safe}</div>', None

    try:
        health = check_health()
        if not health.get("mapper_available"):
            return _err(
                "Mapper LLM is NOT available — document generation requires LLM #1 "
                "(rules fallback is disabled).\n\n"
                f"Configured: {health.get('mapper_provider')}/{health.get('mapper_model')}\n\n"
                "Fix credentials in .env, restart the API, then Refresh API status."
            )
    except ApiError as exc:
        return _err(f"Cannot reach API: {exc}")

    template_path = _resolve_gradio_path(template_file)
    if not template_path:
        return _err("Upload a Word .docx template.")
    if not template_path.lower().endswith(".docx"):
        return _err("Template must be a .docx file.")

    try:
        data = _resolve_json_payload(json_file, json_text)
    except json.JSONDecodeError as exc:
        return _err(f"Invalid JSON: {exc}")
    except ValueError as exc:
        return _err(str(exc))

    try:
        accepted = create_document_job(
            template_path,
            data,
            skip_validation=skip_validation,
        )
        job_id = accepted["job_id"]
        status = wait_for_job(job_id)
    except ApiError as exc:
        return _err(f"API error: {exc}")
    except Exception as exc:  # noqa: BLE001
        return _err(f"Error: {exc}")

    if status.get("status") != "completed":
        err = status.get("error_message") or "Unknown failure"
        return _err(f"Job {job_id} failed.\n\n{err}")

    out_name = Path(status.get("output_path") or "").name
    if not out_name.endswith(".docx"):
        from document_processing_agenticflow.services.naming import build_contract_output_filename

        out_name = build_contract_output_filename(job_id, template_path.name)
    tmp = Path(tempfile.gettempdir()) / out_name
    try:
        download_job_output(job_id, tmp)
    except ApiError as exc:
        return _err(f"Generated but download failed: {exc}")

    conf = status.get("confidence") or {}
    pct = status.get("scores_pct") or conf.get("scores_pct") or {}
    validation = status.get("validation") or {}

    def _p(key: str, fallback_key: str | None = None) -> str:
        val = pct.get(key)
        if val is None and fallback_key:
            raw = conf.get(fallback_key)
            if isinstance(raw, (int, float)):
                val = round(float(raw) * 100, 1)
        if val is None:
            return "n/a"
        return f"{float(val):.1f}%"

    def _esc(value: object) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

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
  <table style="width:100%;border-collapse:collapse;font-size:0.92rem">
    <thead><tr>{head}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</section>
"""

    mapper_llm = _esc(status.get("mapper_llm") or conf.get("mapper_llm") or "")
    validator_llm = _esc(status.get("validator_llm") or conf.get("validator_llm") or "")
    mapper_ok = bool(mapper_llm and mapper_llm != "—")
    validator_ok = bool(validator_llm and validator_llm != "—")

    def _avail(ok: bool) -> str:
        color = "#9EF0B8" if ok else "#FF9A9A"
        label = "available" if ok else "NOT available"
        return (
            f'<span style="display:inline-flex;align-items:center;gap:0.4rem">'
            f'<span style="width:0.55rem;height:0.55rem;border-radius:50%;'
            f"background:{color};display:inline-block\"></span>"
            f"<span style=\"color:{color}\">{label}</span></span>"
        )

    sections = [
        _table(
            "Job",
            ["Field", "Value"],
            [
                ["Job ID", f"<code>{_esc(job_id)}</code>"],
                ["xid", f"<code>{_esc(status.get('xid') or '')}</code>"],
                ["Status", "<strong>completed</strong>"],
            ],
        ),
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
                [
                    "<strong>Overall confidence</strong>",
                    f"<strong>{_p('overall_confidence_pct', 'overall_confidence')}</strong>",
                ],
                [
                    "Placeholder mapping (LLM #1)",
                    _p("placeholder_mapping_confidence_pct", "mapping_confidence"),
                ],
                [
                    "Placeholder coverage",
                    _p("placeholder_coverage_pct", "coverage_score"),
                ],
                [
                    "Table mapping (LLM #1)",
                    _p("table_mapping_confidence_pct", "table_mapping_confidence"),
                ],
                [
                    "Generation integrity",
                    _p("generation_integrity_pct", "generation_integrity"),
                ],
                [
                    "<strong>Document validation (LLM #2)</strong>",
                    f"<strong>{_p('validation_score_pct', 'validation_score')}</strong>",
                ],
            ],
        ),
    ]

    if validation:
        sections.append(
            _table(
                "Validation detail (LLM #2)",
                ["Field", "Value"],
                [
                    ["Passed", f"<code>{_esc(validation.get('passed'))}</code>"],
                    [
                        "Score",
                        f"<code>{_p('validation_score_pct', 'validation_score')}</code>",
                    ],
                    ["Summary", _esc(validation.get("summary") or "—")],
                ],
            )
        )
        issues = validation.get("issues") or []
        if issues:
            issue_rows = [
                [
                    _esc(issue.get("severity") or "—"),
                    f"<code>{_esc(issue.get('field') or '')}</code>",
                    _esc(issue.get("message") or ""),
                ]
                for issue in issues[:10]
            ]
            sections.append(
                _table(
                    "Validation issues (LLM #2)",
                    ["Severity", "Field", "Message"],
                    issue_rows,
                )
            )

    per_ph = pct.get("per_placeholder") or []
    if per_ph:
        ph_rows = [
            [
                f"<code>{_esc(item.get('placeholder'))}</code>",
                f"<code>{_esc(item.get('json_path'))}</code>",
                f"<strong>{float(item.get('confidence_pct', 0)):.1f}%</strong>",
            ]
            for item in per_ph[:20]
        ]
        sections.append(
            _table(
                "Placeholder mapping confidence (LLM #1)",
                ["Placeholder", "JSON path", "Confidence"],
                ph_rows,
            )
        )

    per_col = pct.get("per_table_column") or []
    if per_col:
        col_rows = [
            [
                f"<code>{_esc(item.get('header'))}</code>",
                f"<code>{_esc(item.get('json_field'))}</code>",
                f"<strong>{float(item.get('confidence_pct', 0)):.1f}%</strong>",
            ]
            for item in per_col[:20]
        ]
        sections.append(
            _table(
                "Table column mapping confidence (LLM #1)",
                ["Header", "JSON field", "Confidence"],
                col_rows,
            )
        )

    from document_processing_agenticflow.core.settings import settings as _settings

    db_path = _settings().sqlite_database_path
    sections.append(
        _table(
            "Persistence",
            ["Field", "Value"],
            [
                ["Stored in SQLite", "<strong>yes</strong>"],
                ["xid", f"<code>{_esc(status.get('xid') or '')}</code>"],
                ["Database", f"<code>{_esc(db_path)}</code>"],
                ["Tables", "<code>document_jobs</code>, <code>call_logs</code>"],
            ],
        )
    )

    report = (
        '<div style="font-size:0.95rem;line-height:1.4">'
        + "".join(sections)
        + "</div>"
    )
    return report, str(tmp)


def ui_health() -> str:
    cfg = settings()
    try:
        health = check_health()
    except Exception as exc:  # noqa: BLE001 — API down / network
        return (
            f"<p><strong>API unreachable</strong> at <code>{cfg.api_base_url}</code></p>"
            f"<p>Start the backend:</p>"
            f"<pre>python run_both.py</pre>"
            f"<p>Error: {exc}</p>"
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

    warn = ""
    if not mapper_ok:
        warn = (
            "<p style='color:#FFD0A8'><strong>Document generate is blocked until "
            "mapper LLM is available.</strong> Check credentials in "
            "<code>.env</code> and restart the API.</p>"
        )

    return f"""
<div style="font-size:0.95rem;line-height:1.45">
  <p><strong>API:</strong> <code>{cfg.api_base_url}</code>
     · status <code>{health.get('status', 'ok')}</code></p>

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
        <td style="padding:0.45rem 0.6rem"><strong>document_process_mcp</strong></td>
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


def _html_esc(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pretty_json(value: object, *, limit: int = 4000) -> str:
    if value is None:
        return "—"
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
    except Exception:
        try:
            from document_processing_agenticflow.storage.job_store import JobStore

            jobs = JobStore().list_document_jobs(limit=int(limit))
        except Exception as exc:  # noqa: BLE001
            return f'<div style="color:#FFC4C4">Failed to list jobs: {_html_esc(exc)}</div>'

    if not jobs:
        return "<p>No document jobs in SQLite yet. Generate a document first.</p>"

    rows = []
    for job in jobs:
        xid = job.get("xid") or ""
        rows.append(
            "<tr>"
            f"<td style='padding:0.35rem 0.5rem'><code>{_html_esc(job.get('job_id'))}</code></td>"
            f"<td style='padding:0.35rem 0.5rem'><code>{_html_esc(xid)}</code></td>"
            f"<td style='padding:0.35rem 0.5rem'>{_html_esc(job.get('status'))}</td>"
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
    except Exception:
        try:
            from document_processing_agenticflow.storage.job_store import JobStore

            payload = JobStore().get_trace_by_xid(corr)
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
        latency_s = f"{float(latency):.0f} ms" if isinstance(latency, (int, float)) else "—"
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
    cfg = settings()

    with gr.Blocks(title="Document Processing Agentic Flow") as demo:
        gr.Markdown(
            "# Document Processing Agentic Flow\n"
            "Upload template + JSON to generate Word doc · Record or upload audio to text"
        )

        with gr.Row():
            health_box = gr.HTML(value=ui_health())

        # ------------------------------------------------------------------ Document (1st)
        with gr.Tab("Generate Document"):
            gr.Markdown(
                f"**Upload** a `.docx` template and **upload or paste** JSON data. "
                f"Job runs on `{cfg.api_base_url}/api/v1/documents/jobs`."
            )
            with gr.Row():
                with gr.Column():
                    template_upload = gr.File(
                        label="Upload Word template (.docx)",
                        file_types=[".docx"],
                        file_count="single",
                        type="filepath",
                    )
                    json_file_upload = gr.File(
                        label="Upload JSON data file (.json)",
                        file_types=[".json"],
                        file_count="single",
                        type="filepath",
                    )
                    with gr.Accordion("Or paste JSON", open=False):
                        json_input = gr.Textbox(
                            label="JSON data model (used when no .json file uploaded)",
                            lines=12,
                            placeholder='{"invoice_number": "INV-001", "customer": {"name": "Acme"}}',
                        )
                    skip_validation = gr.Checkbox(label="Skip LLM #2 validation", value=False)
                    generate_btn = gr.Button("Generate document", variant="primary")
                with gr.Column():
                    job_report = gr.HTML(label="Job result")
                    output_file = gr.File(
                        label="Download generated .docx",
                        type="filepath",
                        interactive=False,
                    )

            generate_btn.click(
                fn=ui_generate_document,
                inputs=[template_upload, json_file_upload, json_input, skip_validation],
                outputs=[job_report, output_file],
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

            def _chat_submit(message, history, pending):
                new_history, new_pending, txt, docx = ui_contract_chat(
                    message, history, pending
                )
                return new_history, new_pending, "", txt, docx

            chat_send.click(
                fn=_chat_submit,
                inputs=[chat_input, chatbot, chat_pending],
                outputs=[
                    chatbot,
                    chat_pending,
                    chat_input,
                    contract_text_file,
                    contract_docx_file,
                ],
            )
            chat_input.submit(
                fn=_chat_submit,
                inputs=[chat_input, chatbot, chat_pending],
                outputs=[
                    chatbot,
                    chat_pending,
                    chat_input,
                    contract_text_file,
                    contract_docx_file,
                ],
            )
            audio_send.click(
                fn=ui_contract_chat_from_audio,
                inputs=[audio_input, chatbot, chat_pending, language, provider],
                outputs=[
                    chatbot,
                    chat_pending,
                    contract_text_file,
                    contract_docx_file,
                    transcript_note,
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

        refresh_health = gr.Button("Refresh API status")
        refresh_health.click(fn=ui_health, outputs=[health_box])

    return demo


def main() -> None:
    cfg = settings()
    app = build_ui()
    app.launch(
        server_name=cfg.gradio_host,
        server_port=cfg.gradio_port,
        share=False,
    )


if __name__ == "__main__":
    main()
