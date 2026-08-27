"""Detect fill tokens, stamp LLM marker plans, closest library match."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from docx import Document

from document_processing_mcp.services.library_match import (
    find_closest_library_template,
    similarity_score,
)
from document_processing_mcp.services.marker_apply import apply_marker_plan, normalize_marker_token
from document_processing_mcp.services.placeholders import template_has_markers
from document_processing_mcp.services.prompts.loader import load_prompt_yaml
from document_processing_mcp.services.style_extractor import extract_word_styles
from doc_sample_template import build_sample_template


def test_invoice_template_has_markers(tmp_path: Path) -> None:
    path = build_sample_template(tmp_path / "inv.docx")
    extracted = extract_word_styles(path)
    has, keys = template_has_markers(extracted)
    assert has
    assert "invoice_number" in keys or any("invoice" in k.lower() for k in keys)


def test_plain_docx_has_no_markers(tmp_path: Path) -> None:
    path = tmp_path / "plain.docx"
    doc = Document()
    doc.add_paragraph("Customer Name: Acme Corporation")
    doc.add_paragraph("Effective Date: August 28, 2026")
    doc.save(path)
    extracted = extract_word_styles(path)
    has, keys = template_has_markers(extracted, template_path=str(path))
    assert not has
    assert keys == []


def test_apply_marker_plan_replaces_sample_text(tmp_path: Path) -> None:
    src = tmp_path / "plain.docx"
    doc = Document()
    doc.add_paragraph("Customer Name: Acme Corporation")
    doc.save(src)
    plan = SimpleNamespace(
        markers=[
            SimpleNamespace(
                sample_value="Acme Corporation",
                marker="<customer_name>",
                confidence="HIGH",
            )
        ],
        tables=[],
    )
    dest = tmp_path / "marked.docx"
    result = apply_marker_plan(src, dest, plan)
    assert result["markers_present"]
    extracted = extract_word_styles(dest)
    assert "customer_name" in extracted.placeholders
    text = "\n".join(b.text for b in extracted.blocks)
    assert "<customer_name>" in text
    assert "Acme Corporation" not in text


def test_normalize_marker_token() -> None:
    assert normalize_marker_token("Customer Name") == "<customer_name>"
    assert normalize_marker_token("<already_ok>") == "<already_ok>"


def test_similarity_prefers_overlapping_prose() -> None:
    assert similarity_score("product pricing catalog items", "product pricing list") > 0.2
    assert similarity_score("aaa", "zzz") == 0.0


def test_closest_library_skips_self(tmp_path: Path, monkeypatch) -> None:
    from document_processing_mcp.services import library_match

    monkeypatch.setattr(library_match, "library_template_dirs", lambda: [tmp_path])
    a = tmp_path / "a.docx"
    b = tmp_path / "b.docx"
    da, db = Document(), Document()
    da.add_paragraph("GPO agreement product pricing catalog items")
    db.add_paragraph("GPO agreement product pricing catalog services")
    da.save(a)
    db.save(b)
    extracted = extract_word_styles(a)
    match = find_closest_library_template(extracted, exclude_path=a)
    assert match is not None
    assert Path(match["path"]).name == "b.docx"


def test_marker_synthesizer_prompt_versioned() -> None:
    payload = load_prompt_yaml("marker_synthesizer.yml")
    assert payload["version"] == "1.0.0"
    assert payload["required_version"] == "1.0.0"
    assert "snake_case" in payload["system"]
    assert "{document_text}" in payload["human"]
    assert "{reference_placeholders_json}" in payload["human"]
