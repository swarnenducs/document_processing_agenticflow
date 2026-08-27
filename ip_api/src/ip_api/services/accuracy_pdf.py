"""Build a printable PDF of the document-job accuracy / confidence report."""

from __future__ import annotations

import re
from typing import Any

from fpdf import FPDF

NAVY = (15, 23, 42)
WHITE = (255, 255, 255)
SLATE = (51, 65, 85)
LINE = (226, 232, 240)
RED = (185, 28, 28)
RED_BG = (254, 226, 226)
GREEN = (21, 128, 61)
GREEN_BG = (220, 252, 231)
AMBER = (161, 98, 7)
AMBER_BG = (254, 243, 199)

_SCORE_ROWS = (
    ("Overall confidence", "overall_confidence_pct"),
    ("Extraction confidence", "extraction_confidence_pct"),
    ("Extraction placeholder detection", "extraction_placeholder_detection_pct"),
    ("Extraction structure", "extraction_structure_pct"),
    ("Placeholder mapping (LLM #1)", "placeholder_mapping_confidence_pct"),
    ("Placeholder coverage", "placeholder_coverage_pct"),
    ("Table mapping (LLM #1)", "table_mapping_confidence_pct"),
    ("Generation integrity", "generation_integrity_pct"),
    ("Generation confidence", "generation_confidence_pct"),
    ("Document validation (LLM #2)", "validation_score_pct"),
)


def accuracy_pdf_filename(job_id: str) -> str:
    """Download name is the job id, e.g. ``{job_id}.pdf``."""
    safe = re.sub(r"[^\w.\-]+", "_", (job_id or "").strip(), flags=re.ASCII)
    safe = safe.strip("._") or "job"
    return f"{safe}.pdf"


UNMARKED_TEMPLATE_NOTE = (
    "The template was unmarked, so the AI took extra time to understand the document."
)


def _marker_detection(report: dict[str, Any], job: dict[str, Any]) -> dict[str, Any] | None:
    for blob in (report, job):
        if not isinstance(blob, dict):
            continue
        md = blob.get("marker_detection")
        if isinstance(md, dict):
            return md
        result = blob.get("result")
        if isinstance(result, dict) and isinstance(result.get("marker_detection"), dict):
            return result["marker_detection"]
    return None


def unmarked_template_report_rows(
    report: dict[str, Any],
    job: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Rows for PDF/UI when the uploaded Word file had no fill markers."""
    detection = _marker_detection(report, job or {})
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
        ("Template markers", "Unmarked"),
        ("Processing note", UNMARKED_TEMPLATE_NOTE),
        ("Reference closest-match template", closest),
    ]


def _text(value: object, *, limit: int = 4000) -> str:
    raw = "" if value is None else str(value)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = raw.encode("latin-1", "replace").decode("latin-1")
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "..."
    return cleaned


def _as_pct(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_band(pct: float | None) -> str:
    """red < 80, amber 80-90 exclusive of green, green >= 90."""
    if pct is None:
        return "none"
    if pct < 80:
        return "red"
    if pct >= 90:
        return "green"
    return "amber"


def _band_colors(band: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if band == "red":
        return RED_BG, RED
    if band == "green":
        return GREEN_BG, GREEN
    if band == "amber":
        return AMBER_BG, AMBER
    return WHITE, SLATE


def _fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "n/a"
    return f"{pct:.1f}%"


class _AccuracyPDF(FPDF):
    def __init__(self, job_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._job_id = job_id

    def header(self) -> None:
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 22, "F")
        self.set_xy(self.l_margin, 5)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 6, "Document accuracy report", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, f"Job  {self._job_id}", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.set_y(26)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 8, f"{self._job_id}   |   Page {self.page_no()}/{{nb}}", align="C")
        self.set_text_color(0, 0, 0)


def _need_page(pdf: _AccuracyPDF, height: float) -> None:
    if pdf.get_y() + height > pdf.page_break_trigger:
        pdf.add_page()


def _section(pdf: _AccuracyPDF, title: str) -> None:
    _need_page(pdf, 14)
    pdf.ln(3)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _text(title), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    pdf.ln(1)


def _wrapped_row(
    pdf: _AccuracyPDF,
    cells: list[str],
    widths: list[float],
    *,
    fills: list[tuple[int, int, int] | None] | None = None,
    texts: list[tuple[int, int, int] | None] | None = None,
    line_h: float = 5.0,
    header: bool = False,
) -> None:
    pdf.set_font("Helvetica", "B" if header else "", 8)
    lines_per: list[list[str]] = []
    max_lines = 1
    for text, width in zip(cells, widths, strict=True):
        chunk = _text(text, limit=8000)
        try:
            wrapped = pdf.multi_cell(width, line_h, chunk, dry_run=True, output="LINES")
        except TypeError:
            wrapped = pdf.multi_cell(width, line_h, chunk, split_only=True)
        if isinstance(wrapped, str):
            wrapped = wrapped.split("\n")
        lines_per.append(wrapped or [""])
        max_lines = max(max_lines, len(lines_per[-1]))
    row_h = max_lines * line_h
    _need_page(pdf, row_h + 1)
    x0 = pdf.get_x()
    y0 = pdf.get_y()
    fills = fills or [None] * len(cells)
    texts = texts or [None] * len(cells)
    for i, (width, wrapped, fill, color) in enumerate(
        zip(widths, lines_per, fills, texts, strict=True)
    ):
        x = x0 + sum(widths[:i])
        if fill:
            pdf.set_fill_color(*fill)
            pdf.rect(x, y0, width, row_h, "F")
        pdf.set_xy(x, y0)
        pdf.set_text_color(*(color or ((255, 255, 255) if header else (15, 23, 42))))
        pdf.rect(x, y0, width, row_h)
        pdf.multi_cell(width, line_h, "\n".join(wrapped), border=0)
    pdf.set_xy(x0, y0 + row_h)
    pdf.set_text_color(0, 0, 0)


def _kv_table(pdf: _AccuracyPDF, rows: list[tuple[str, str]]) -> None:
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    widths = [usable * 0.32, usable * 0.68]
    _wrapped_row(
        pdf,
        ["Field", "Value"],
        widths,
        fills=[NAVY, NAVY],
        texts=[WHITE, WHITE],
        header=True,
    )
    for i, (left, right) in enumerate(rows):
        shade = (248, 250, 252) if i % 2 == 0 else WHITE
        _wrapped_row(
            pdf,
            [left, right],
            widths,
            fills=[shade, shade],
        )


def _score_row(pdf: _AccuracyPDF, label: str, pct: float | None, widths: list[float]) -> None:
    band = score_band(pct)
    bg, fg = _band_colors(band)
    _wrapped_row(
        pdf,
        [label, _fmt_pct(pct)],
        widths,
        fills=[WHITE, bg],
        texts=[NAVY, fg],
    )


def _collect_scores(report: dict[str, Any]) -> dict[str, Any]:
    scores = report.get("scores_pct") if isinstance(report.get("scores_pct"), dict) else {}
    if scores:
        return scores
    return {
        "overall_confidence_pct": report.get("overall_confidence_pct"),
        "extraction_confidence_pct": report.get("extraction_confidence_pct"),
        "placeholder_mapping_confidence_pct": report.get("mapping_confidence_pct"),
        "placeholder_coverage_pct": report.get("coverage_pct"),
        "table_mapping_confidence_pct": report.get("table_mapping_confidence_pct"),
        "generation_integrity_pct": report.get("generation_integrity_pct"),
        "generation_confidence_pct": report.get("generation_confidence_pct"),
        "validation_score_pct": report.get("validation_score_pct"),
        "per_placeholder": [],
        "per_table_column": [],
    }


def build_accuracy_report_pdf(
    *,
    job_id: str,
    report: dict[str, Any],
    job: dict[str, Any] | None = None,
) -> bytes:
    """Full accuracy report PDF. Filename should be ``accuracy_pdf_filename(job_id)``."""
    job = job or {}
    scores = _collect_scores(report)
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    if not validation and isinstance(job.get("validation"), dict):
        validation = job["validation"]
    extraction = report.get("extraction_validation")
    if not isinstance(extraction, dict):
        extraction = {}

    pdf = _AccuracyPDF(job_id, orientation="P", unit="mm", format="A4")
    pdf.compress = False
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(14, 28, 14)
    pdf.add_page()

    usable = pdf.w - pdf.l_margin - pdf.r_margin
    overall = _as_pct(scores.get("overall_confidence_pct"))
    band = score_band(overall)
    bg, fg = _band_colors(band)
    _need_page(pdf, 22)
    y = pdf.get_y()
    pdf.set_fill_color(*bg)
    pdf.rect(pdf.l_margin, y, usable, 16, "F")
    pdf.set_xy(pdf.l_margin + 3, y + 2)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*SLATE)
    pdf.cell(usable * 0.55, 5, "Overall confidence")
    pdf.set_xy(pdf.l_margin + 3, y + 7)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*fg)
    pdf.cell(usable * 0.55, 7, _fmt_pct(overall))
    pdf.set_xy(pdf.l_margin + usable * 0.55, y + 4)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*SLATE)
    pdf.multi_cell(
        usable * 0.45,
        4,
        "Red < 80%   Amber 80-89.9%   Green >= 90%",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y + 18)

    _section(pdf, "Job")
    job_rows = [
        ("Job ID", job_id),
        ("xid", str(report.get("xid") or job.get("xid") or "")),
        ("Status", str(job.get("status") or "completed")),
        ("MCP", str(report.get("mcp") or job.get("mcp") or "document_process_mcp")),
        ("Overall time", str(report.get("elapsed") or job.get("elapsed") or "n/a")),
        ("Mapper LLM", str(report.get("mapper_llm") or job.get("mapper_llm") or "")),
        ("Validator LLM", str(report.get("validator_llm") or job.get("validator_llm") or "")),
        ("Created", str(report.get("created_at") or "")),
    ]
    unmarked = unmarked_template_report_rows(report, job)
    if unmarked:
        job_rows.extend(unmarked)
    _kv_table(pdf, job_rows)

    _section(pdf, "Scores")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*SLATE)
    pdf.multi_cell(
        0,
        4,
        "Legend: red = below 80%   |   amber = 80% to 89.9%   |   green = 90% or above",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)
    score_widths = [usable * 0.72, usable * 0.28]
    _wrapped_row(
        pdf,
        ["Metric", "Score"],
        score_widths,
        fills=[NAVY, NAVY],
        texts=[WHITE, WHITE],
        header=True,
    )
    for label, key in _SCORE_ROWS:
        _score_row(pdf, label, _as_pct(scores.get(key)), score_widths)

    if extraction:
        _section(pdf, "Extraction critic")
        _kv_table(
            pdf,
            [
                ("Passed", str(extraction.get("passed"))),
                ("Summary", str(extraction.get("summary") or "-")),
                (
                    "Missed placeholders",
                    ", ".join(str(x) for x in (extraction.get("missed_placeholder_suspects") or []))
                    or "-",
                ),
            ],
        )

    if validation:
        _section(pdf, "Validation detail (LLM #2)")
        _kv_table(
            pdf,
            [
                ("Passed", str(validation.get("passed"))),
                ("Score", _fmt_pct(_as_pct(scores.get("validation_score_pct")))),
                ("Summary", str(validation.get("summary") or "-")),
            ],
        )
        issues = validation.get("issues") or []
        if isinstance(issues, list) and issues:
            _section(pdf, "Validation issues")
            issue_w = [usable * 0.16, usable * 0.28, usable * 0.56]
            _wrapped_row(
                pdf,
                ["Severity", "Field", "Message"],
                issue_w,
                fills=[NAVY, NAVY, NAVY],
                texts=[WHITE, WHITE, WHITE],
                header=True,
            )
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                _wrapped_row(
                    pdf,
                    [
                        str(issue.get("severity") or "-"),
                        str(issue.get("field") or ""),
                        str(issue.get("message") or ""),
                    ],
                    issue_w,
                )

    per_ph = scores.get("per_placeholder") or []
    if isinstance(per_ph, list) and per_ph:
        _section(pdf, "Placeholder mapping (LLM #1)")
        ph_w = [usable * 0.28, usable * 0.28, usable * 0.14, usable * 0.30]
        _wrapped_row(
            pdf,
            ["Placeholder", "JSON path", "Score", "Rationale"],
            ph_w,
            fills=[NAVY, NAVY, NAVY, NAVY],
            texts=[WHITE, WHITE, WHITE, WHITE],
            header=True,
        )
        for item in per_ph:
            if not isinstance(item, dict):
                continue
            pct = _as_pct(item.get("confidence_pct"))
            if pct is None:
                pct = _as_pct(item.get("confidence"))
                if pct is not None and pct <= 1.0:
                    pct = pct * 100.0
            band = score_band(pct)
            bg, fg = _band_colors(band)
            _wrapped_row(
                pdf,
                [
                    str(item.get("placeholder") or ""),
                    str(item.get("json_path") or ""),
                    _fmt_pct(pct),
                    str(item.get("rationale") or ""),
                ],
                ph_w,
                fills=[WHITE, WHITE, bg, WHITE],
                texts=[NAVY, NAVY, fg, SLATE],
            )

    per_col = scores.get("per_table_column") or []
    if isinstance(per_col, list) and per_col:
        _section(pdf, "Table column mapping (LLM #1)")
        col_w = [usable * 0.10, usable * 0.28, usable * 0.28, usable * 0.14, usable * 0.20]
        _wrapped_row(
            pdf,
            ["Tbl", "Header", "JSON field", "Score", "Array path"],
            col_w,
            fills=[NAVY] * 5,
            texts=[WHITE] * 5,
            header=True,
        )
        for item in per_col:
            if not isinstance(item, dict):
                continue
            pct = _as_pct(item.get("confidence_pct"))
            if pct is None:
                pct = _as_pct(item.get("confidence"))
                if pct is not None and pct <= 1.0:
                    pct = pct * 100.0
            band = score_band(pct)
            bg, fg = _band_colors(band)
            _wrapped_row(
                pdf,
                [
                    str(item.get("table_index") if item.get("table_index") is not None else ""),
                    str(item.get("header") or ""),
                    str(item.get("json_field") or ""),
                    _fmt_pct(pct),
                    str(item.get("array_json_path") or ""),
                ],
                col_w,
                fills=[WHITE, WHITE, WHITE, bg, WHITE],
                texts=[NAVY, NAVY, NAVY, fg, SLATE],
            )

    notes = report.get("notes")
    if notes:
        _section(pdf, "Notes")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _text(notes, limit=8000))

    out = pdf.output()
    return bytes(out)
