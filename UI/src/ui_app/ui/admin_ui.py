"""Gradio handlers for API-target JSON and admin (templates + master data)."""

from __future__ import annotations

from html import escape as _html_escape

from ui_app.core.ui_config import apply_ui_config, dumps_config, get_api_base_url
from ui_app.ui.api_client import (
    ApiError,
    delete_master_data,
    list_admin_templates,
    list_master_data,
    upsert_master_data,
    upload_admin_template,
)


def ui_config_json() -> str:
    return dumps_config()


def ui_apply_api_config(raw_json: str):
    from ui_app.ui.gradio_app import _error_banner, ui_health

    try:
        apply_ui_config(raw_json)
    except Exception as exc:  # noqa: BLE001
        return dumps_config(), _error_banner("Invalid API config JSON", str(exc))
    return dumps_config(), ui_health()


def ui_api_target_caption() -> str:
    return f"**API host:** `{get_api_base_url()}` — edit JSON in **API targets** to switch local vs Azure."


def _esc(value: object) -> str:
    if value is None:
        return ""
    return _html_escape(str(value), quote=True)


def _error(title: str, message: str) -> str:
    from ui_app.ui.gradio_app import _error_banner

    return _error_banner(title, message)


def _file_path(file_obj: object | None) -> str | None:
    from ui_app.ui.gradio_app import _resolve_gradio_path

    return _resolve_gradio_path(file_obj)


def _templates_html(payload: dict) -> str:
    rows = []
    for item in payload.get("templates") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_esc(item.get('folder_name'))}</td>"
            f"<td>{_esc(item.get('template_name'))}</td>"
            f"<td>{_esc(item.get('storage_backend'))}</td>"
            f"<td>{_esc(item.get('size_bytes'))}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4'>No templates (or admin key missing).</td></tr>"
    return (
        f"<p>count={_esc(payload.get('count'))} backend={_esc(payload.get('storage_backend'))}</p>"
        "<table><thead><tr><th>folder</th><th>name</th><th>backend</th><th>bytes</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _master_html(payload: dict) -> str:
    rows = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        preview = str(item.get("content") or "")[:120]
        rows.append(
            "<tr>"
            f"<td>{_esc(item.get('placeholder_key'))}</td>"
            f"<td>{_esc(item.get('category'))}</td>"
            f"<td>{_esc(item.get('active'))}</td>"
            f"<td><pre style='white-space:pre-wrap;max-width:28rem'>{_esc(preview)}</pre></td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4'>No master-data rows.</td></tr>"
    return (
        f"<p>count={_esc(payload.get('count'))}</p>"
        "<table><thead><tr><th>placeholder_key</th><th>category</th><th>active</th>"
        "<th>content (preview)</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def ui_list_templates(folder_name: str) -> str:
    try:
        folder = (folder_name or "").strip() or None
        return _templates_html(list_admin_templates(folder_name=folder))
    except ApiError as exc:
        return _error("List templates failed", str(exc))


def ui_upload_template(file_obj: object | None, folder_name: str, template_name: str) -> str:
    path = _file_path(file_obj)
    if not path:
        return _error("Upload failed", "Choose a .docx file")
    try:
        rec = upload_admin_template(
            path,
            folder_name=(folder_name or "").strip() or "ipp_pricing_default_template",
            template_name=(template_name or "").strip() or None,
        )
        listing = list_admin_templates(
            folder_name=(folder_name or "").strip() or "ipp_pricing_default_template"
        )
        loc = rec.get("location") or rec.get("template_name")
        return f"<p>Saved <code>{_esc(loc)}</code></p>" + _templates_html(listing)
    except ApiError as exc:
        return _error("Upload failed", str(exc))


def ui_list_master() -> str:
    try:
        return _master_html(list_master_data())
    except ApiError as exc:
        return _error("List master data failed", str(exc))


def ui_save_master(placeholder_key: str, category: str, content: str, active: bool) -> str:
    key = (placeholder_key or "").strip()
    if not key or not (content or "").strip():
        return _error("Save failed", "placeholder_key and content are required")
    try:
        rec = upsert_master_data(
            placeholder_key=key,
            content=content,
            category=(category or "").strip() or None,
            active=bool(active),
        )
        return (
            f"<p>Saved <code>{_esc(rec.get('placeholder_key'))}</code></p>"
            + _master_html(list_master_data())
        )
    except ApiError as exc:
        return _error("Save master data failed", str(exc))


def ui_delete_master(placeholder_key: str) -> str:
    key = (placeholder_key or "").strip()
    if not key:
        return _error("Delete failed", "placeholder_key is required")
    try:
        delete_master_data(key)
        return f"<p>Deleted <code>{_esc(key)}</code></p>" + _master_html(list_master_data())
    except ApiError as exc:
        return _error("Delete master data failed", str(exc))
