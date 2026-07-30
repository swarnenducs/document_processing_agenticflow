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
    run_voice_contract_audio,
    run_voice_contract_text,
    wait_for_job,
)

# Allow: python -m document_processing_agenticflow.ui.gradio_app
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_TEMPLATE = PROJECT_ROOT / "samples" / "templates" / "invoice_template.docx"
SAMPLE_JSON = PROJECT_ROOT / "samples" / "data" / "invoice.json"
# User-provided contract example (from Downloads: Contract Template.docx + dummy products.json)
CONTRACT_TEMPLATE = PROJECT_ROOT / "samples" / "templates" / "contract_template.docx"
CONTRACT_JSON = PROJECT_ROOT / "samples" / "data" / "dummy_products.json"
CONTACTS_JSON = PROJECT_ROOT / "samples" / "data" / "contacts.json"


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
    try:
        health = check_health()
        if not health.get("mapper_available"):
            return (
                "**Mapper LLM is NOT available** — document generation requires LLM #1 "
                "(rules fallback is disabled).\n\n"
                f"Configured: `{health.get('mapper_provider')}/{health.get('mapper_model')}`\n\n"
                "Fix credentials in `.env`, restart the API, then **Refresh API status**.",
                None,
            )
    except ApiError as exc:
        return f"Cannot reach API: {exc}", None

    template_path = _resolve_gradio_path(template_file)
    if not template_path:
        return "Upload a Word `.docx` template.", None
    if not template_path.lower().endswith(".docx"):
        return "Template must be a `.docx` file.", None

    try:
        data = _resolve_json_payload(json_file, json_text)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}", None
    except ValueError as exc:
        return str(exc), None

    try:
        accepted = create_document_job(
            template_path,
            data,
            skip_validation=skip_validation,
        )
        job_id = accepted["job_id"]
        status = wait_for_job(job_id)
    except ApiError as exc:
        return f"API error: {exc}", None
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", None

    if status.get("status") != "completed":
        err = status.get("error_message") or "Unknown failure"
        return f"Job `{job_id}` failed.\n\n{err}", None

    tmp = Path(tempfile.gettempdir()) / f"gradio_{job_id}.docx"
    try:
        download_job_output(job_id, tmp)
    except ApiError as exc:
        return f"Generated but download failed: {exc}", None

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

    report = (
        f"**Job ID:** `{job_id}`  \n"
        f"**Status:** completed  \n\n"
        f"### LLMs\n"
        f"- **LLM #1 (mapper):** `{status.get('mapper_llm') or conf.get('mapper_llm')}`  \n"
        f"- **LLM #2 (validator):** `{status.get('validator_llm') or conf.get('validator_llm')}`  \n\n"
        f"### Scores (all in %)\n"
        f"| Metric | Score |\n|---|---|\n"
        f"| **Overall confidence** | **{_p('overall_confidence_pct', 'overall_confidence')}** |\n"
        f"| Placeholder mapping (LLM #1) | {_p('placeholder_mapping_confidence_pct', 'mapping_confidence')} |\n"
        f"| Placeholder coverage | {_p('placeholder_coverage_pct', 'coverage_score')} |\n"
        f"| Table mapping (LLM #1) | {_p('table_mapping_confidence_pct', 'table_mapping_confidence')} |\n"
        f"| Generation integrity | {_p('generation_integrity_pct', 'generation_integrity')} |\n"
        f"| **Document validation (LLM #2)** | **{_p('validation_score_pct', 'validation_score')}** |\n"
    )

    if validation:
        report += (
            f"\n### Validation detail (LLM #2)\n"
            f"- **Passed:** `{validation.get('passed')}`  \n"
            f"- **Score:** `{_p('validation_score_pct', 'validation_score')}`  \n"
            f"- **Summary:** {validation.get('summary') or '—'}  \n"
        )
        issues = validation.get("issues") or []
        if issues:
            report += "\n**Issues:**\n"
            for issue in issues[:10]:
                field = issue.get("field") or ""
                report += f"- ({issue.get('severity')}) {field}: {issue.get('message')}\n"

    per_ph = pct.get("per_placeholder") or []
    if per_ph:
        report += "\n### Placeholder mapping confidence (LLM #1)\n"
        for item in per_ph[:12]:
            report += (
                f"- `{item.get('placeholder')}` → `{item.get('json_path')}`: "
                f"**{item.get('confidence_pct', 0):.1f}%**\n"
            )

    per_col = pct.get("per_table_column") or []
    if per_col:
        report += "\n### Table column mapping confidence (LLM #1)\n"
        for item in per_col[:12]:
            report += (
                f"- `{item.get('header')}` → `{item.get('json_field')}`: "
                f"**{item.get('confidence_pct', 0):.1f}%**\n"
            )

    return report, str(tmp)


def load_sample_template() -> str | None:
    if SAMPLE_TEMPLATE.exists():
        return str(SAMPLE_TEMPLATE)
    return None


def load_sample_json_text() -> str:
    if SAMPLE_JSON.exists():
        return SAMPLE_JSON.read_text(encoding="utf-8")
    return '{"invoice_number": "INV-001", "customer": {"name": "Acme"}}'


def load_sample_json_file() -> str | None:
    if SAMPLE_JSON.exists():
        return str(SAMPLE_JSON)
    return None


def load_contract_template() -> str | None:
    if CONTRACT_TEMPLATE.exists():
        return str(CONTRACT_TEMPLATE)
    return None


def load_contract_json_text() -> str:
    if CONTRACT_JSON.exists():
        return CONTRACT_JSON.read_text(encoding="utf-8")
    return '{"DATE": "2026-07-13", "accountName": "Acme", "products": []}'


def load_contract_json_file() -> str | None:
    if CONTRACT_JSON.exists():
        return str(CONTRACT_JSON)
    return None


def ui_health() -> str:
    cfg = settings()
    try:
        health = check_health()
    except Exception as exc:  # noqa: BLE001 — API down / network
        return (
            f"**API unreachable** at `{cfg.api_base_url}`\n\n"
            f"Start the backend:\n\n"
            f"```bash\npython run_both.py\n```\n\n"
            f"Error: {exc}"
        )

    def _badge(ok: bool) -> str:
        return "✅ available" if ok else "❌ NOT available"

    mapper_ok = bool(health.get("mapper_available"))
    validator_ok = bool(health.get("validator_available"))
    speech_ok = bool(health.get("speech_available"))

    lines = [
        f"**API:** `{cfg.api_base_url}` · status `{health.get('status', 'ok')}`",
        "",
        "### LLM status (required — no rule-based fallback)",
        f"- **LLM #1 Mapper:** {_badge(mapper_ok)} — "
        f"`{health.get('mapper_provider')}/{health.get('mapper_model')}`",
        f"- **LLM #2 Validator:** {_badge(validator_ok)} — "
        f"`{health.get('validator_provider')}/{health.get('validator_model')}`",
        f"- **Speech:** {_badge(speech_ok)} — `{health.get('speech_provider')}`",
        "",
        f"- Storage: `{health.get('storage_base_path')}`",
    ]
    if not mapper_ok:
        lines.extend(
            [
                "",
                "> **Document generate is blocked until mapper LLM is available.** "
                "Set Azure credentials in `.env` and restart the API.",
            ]
        )
    return "\n".join(lines)


def build_ui() -> gr.Blocks:
    cfg = settings()

    with gr.Blocks(title="Document Processing Agentic Flow") as demo:
        gr.Markdown(
            "# Document Processing Agentic Flow\n"
            "Upload template + JSON → generate Word doc · Record or upload audio → text"
        )

        with gr.Row():
            health_box = gr.Markdown(value=ui_health())

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
                    with gr.Row():
                        load_tpl_btn = gr.Button("Load invoice sample", size="sm")
                        load_json_btn = gr.Button("Load invoice JSON", size="sm")
                    with gr.Row():
                        load_contract_tpl_btn = gr.Button("Load contract template", size="sm")
                        load_contract_json_btn = gr.Button("Load dummy products JSON", size="sm")
                    skip_validation = gr.Checkbox(label="Skip LLM #2 validation", value=False)
                    generate_btn = gr.Button("Generate document", variant="primary")
                with gr.Column():
                    job_report = gr.Markdown(label="Job result")
                    output_file = gr.File(
                        label="Download generated .docx",
                        type="filepath",
                        interactive=False,
                    )

            load_tpl_btn.click(fn=load_sample_template, outputs=[template_upload])
            load_json_btn.click(
                fn=load_sample_json_text,
                outputs=[json_input],
            ).then(fn=load_sample_json_file, outputs=[json_file_upload])
            load_contract_tpl_btn.click(fn=load_contract_template, outputs=[template_upload])
            load_contract_json_btn.click(
                fn=load_contract_json_text,
                outputs=[json_input],
            ).then(fn=load_contract_json_file, outputs=[json_file_upload])

            generate_btn.click(
                fn=ui_generate_document,
                inputs=[template_upload, json_file_upload, json_input, skip_validation],
                outputs=[job_report, output_file],
            )

        # ------------------------------------------------------------------ Voice chat (2nd)
        with gr.Tab("Voice → Contract"):
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
