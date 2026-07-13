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
    create_document_job,
    download_job_output,
    transcribe_audio_file,
    wait_for_job,
)

# Allow: python -m document_processing_agenticflow.ui.gradio_app
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_TEMPLATE = PROJECT_ROOT / "samples" / "templates" / "invoice_template.docx"
SAMPLE_JSON = PROJECT_ROOT / "samples" / "data" / "invoice.json"
# User-provided contract example (from Downloads: Contract Template.docx + dummy products.json)
CONTRACT_TEMPLATE = PROJECT_ROOT / "samples" / "templates" / "contract_template.docx"
CONTRACT_JSON = PROJECT_ROOT / "samples" / "data" / "dummy_products.json"


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


def _format_transcription(result: dict) -> tuple[str, str]:
    meta = (
        f"**Transcription ID:** `{result.get('transcription_id')}`\n\n"
        f"**Provider:** `{result.get('provider')}`\n\n"
        f"**Model:** `{result.get('model')}`\n\n"
        f"**Language:** `{result.get('language') or 'auto'}`"
    )
    return result.get("text", ""), meta


def ui_transcribe(
    audio_path: str | None,
    language: str,
    provider: str,
) -> tuple[str, str]:
    path = _resolve_gradio_path(audio_path)
    if not path:
        return "Record or upload audio first.", ""

    try:
        lang = language.strip() or None
        prov = None if provider in {"", "default", "auto"} else provider
        result = transcribe_audio_file(path, language=lang, provider=prov)
        return _format_transcription(result)
    except ApiError as exc:
        return f"API error: {exc}", ""
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", ""


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
    except ApiError as exc:
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

        # ------------------------------------------------------------------ Voice (2nd)
        with gr.Tab("Voice → Text"):
            gr.Markdown(
                "Record from your microphone **or upload** an audio file. "
                f"Sent to `{cfg.api_base_url}/api/v1/audio/transcribe`."
            )
            with gr.Row():
                with gr.Column():
                    audio_input = gr.Audio(
                        label="Record or upload audio",
                        sources=["microphone", "upload"],
                        type="filepath",
                    )
                    language = gr.Textbox(
                        label="Language (optional ISO-639-1, e.g. en)",
                        placeholder="en",
                    )
                    provider = gr.Dropdown(
                        label="Speech provider",
                        choices=["auto", "groq", "openai", "azure_openai"],
                        value="groq",
                        info="Default Groq Whisper; auto picks Azure/OpenAI/Groq from available keys",
                    )
                    transcribe_btn = gr.Button("Transcribe", variant="primary")
                with gr.Column():
                    transcript_out = gr.Textbox(
                        label="Transcript (natural language text)",
                        lines=12,
                    )
                    meta_out = gr.Markdown(label="Metadata")

            transcribe_btn.click(
                fn=ui_transcribe,
                inputs=[audio_input, language, provider],
                outputs=[transcript_out, meta_out],
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
