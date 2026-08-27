from __future__ import annotations

from ui_app.ui.admin_ui import _templates_html, ui_upload_template


def test_templates_html_escapes_integer_size_bytes() -> None:
    html = _templates_html(
        {
            "count": 1,
            "storage_backend": "azure_blob",
            "templates": [
                {
                    "folder_name": "ipp_pricing_default_template",
                    "template_name": "complete_contract_template_GPO.docx",
                    "storage_backend": "azure_blob",
                    "size_bytes": 1048576,
                }
            ],
        }
    )
    assert "1048576" in html
    assert "complete_contract_template_GPO.docx" in html


def test_upload_without_file_asks_for_docx() -> None:
    html = ui_upload_template(None, "ipp_pricing_default_template", "")
    assert "Choose a .docx file" in html
