"""Accuracy report PDF generation."""

from __future__ import annotations

from ip_api.services.accuracy_pdf import (
    accuracy_pdf_filename,
    build_accuracy_report_pdf,
    score_band,
)


def test_accuracy_pdf_filename_is_job_id() -> None:
    assert accuracy_pdf_filename("job-abc") == "job-abc.pdf"
    assert accuracy_pdf_filename("a/b c") == "a_b_c.pdf"


def test_score_band_thresholds() -> None:
    assert score_band(79.9) == "red"
    assert score_band(80.0) == "amber"
    assert score_band(89.9) == "amber"
    assert score_band(90.0) == "green"


def test_accuracy_pdf_contains_metrics() -> None:
    report = {
        "xid": "xid-1",
        "mcp": "document_process_mcp",
        "elapsed": "12.4s",
        "mapper_llm": "groq/openai/gpt-oss-120b",
        "validator_llm": "openai/gpt-4.1-mini",
        "scores_pct": {
            "overall_confidence_pct": 93.9,
            "placeholder_mapping_confidence_pct": 97.7,
            "placeholder_coverage_pct": 100.0,
            "table_mapping_confidence_pct": 76.1,
            "generation_integrity_pct": 100.0,
            "validation_score_pct": 100.0,
            "per_placeholder": [
                {
                    "placeholder": "Legal_Department_Master_Data",
                    "json_path": "Legal_Department_Master_Data",
                    "confidence_pct": 100.0,
                    "rationale": "Exact JSON key match.",
                }
            ],
            "per_table_column": [
                {
                    "header": "COT Code",
                    "json_field": "cot_code",
                    "confidence_pct": 98.0,
                }
            ],
        },
        "validation": {
            "passed": True,
            "summary": "All mapped values from the JSON are correctly reflected.",
            "issues": [
                {"severity": "info", "field": "clause", "message": "Reviewed full clause text."}
            ],
        },
    }
    payload = build_accuracy_report_pdf(
        job_id="job-abc",
        report=report,
        job={"status": "completed"},
    )
    assert payload.startswith(b"%PDF")
    assert b"Document accuracy report" in payload
    assert b"Legal_Department_Master_Data" in payload
    assert b"Exact JSON key match." in payload
    assert b"Reviewed full clause text." in payload
    assert b"COT Code" in payload
    assert b"93.9%" in payload
    assert b"76.1%" in payload
    assert b"Green >= 90%" in payload or b"green = 90%" in payload


def test_accuracy_pdf_includes_unmarked_template_and_closest_match() -> None:
    from ip_api.services.accuracy_pdf import unmarked_template_report_rows

    report = {
        "xid": "xid-u",
        "mcp": "document_process_mcp",
        "elapsed": "2m 10.0s",
        "notes": "The template was unmarked, so the AI took extra time to understand the document.",
        "scores_pct": {"overall_confidence_pct": 80.0},
        "marker_detection": {
            "had_markers": False,
            "library_match": {
                "name": "complete_contract_template_GPO.docx",
                "score": 0.42,
            },
        },
    }
    rows = unmarked_template_report_rows(report, {})
    assert rows[0][1] == "Unmarked"
    assert "extra time to understand the document" in rows[1][1]
    assert "complete_contract_template_GPO.docx" in rows[2][1]
    payload = build_accuracy_report_pdf(job_id="job-unmarked", report=report, job={})
    assert b"complete_contract_template_GPO.docx" in payload
    assert b"unmarked" in payload.lower()
    assert b"extra time to understand the document" in payload
