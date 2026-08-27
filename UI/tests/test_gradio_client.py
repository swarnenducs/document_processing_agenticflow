"""Tests for Gradio UI helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ui_app.ui.api_client import ApiError, transcribe_audio_file
from ui_app.ui.gradio_app import (
    _resolve_gradio_path,
    _resolve_json_payload,
    _unmarked_template_report_rows,
)


def test_resolve_gradio_path_string() -> None:
    assert _resolve_gradio_path("/tmp/a.wav") == "/tmp/a.wav"


def test_resolve_gradio_path_pathlib() -> None:
    assert _resolve_gradio_path(Path("/tmp/d.docx")) == "/tmp/d.docx"


def test_resolve_gradio_path_list() -> None:
    assert _resolve_gradio_path(["/tmp/b.docx"]) == "/tmp/b.docx"


def test_resolve_gradio_path_dict() -> None:
    assert _resolve_gradio_path({"path": "/tmp/c.json"}) == "/tmp/c.json"


def test_resolve_json_payload_from_file(tmp_path: Path) -> None:
    j = tmp_path / "data.json"
    j.write_text('{"a": 1}', encoding="utf-8")
    result = _resolve_json_payload(str(j), "")
    assert result == {"a": 1}


def test_resolve_json_payload_from_text() -> None:
    result = _resolve_json_payload(None, '{"x": 1}')
    assert result == {"x": 1}


def test_resolve_json_payload_file_takes_priority(tmp_path: Path) -> None:
    j = tmp_path / "data.json"
    j.write_text('{"from": "file"}', encoding="utf-8")
    result = _resolve_json_payload(str(j), '{"from": "text"}')
    assert result == {"from": "file"}


def test_transcribe_audio_file_success(tmp_path: Path) -> None:
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-audio")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "transcription_id": "t1",
        "text": "Hello world",
        "provider": "openai",
        "model": "whisper-1",
        "language": "en",
    }

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("ui_app.ui.api_client.httpx.Client", return_value=mock_client):
        result = transcribe_audio_file(audio, language="en")

    assert result["text"] == "Hello world"


def test_transcribe_audio_missing_file() -> None:
    with pytest.raises(ApiError, match="not found"):
        transcribe_audio_file("/nonexistent/audio.wav")


def test_unmarked_template_report_rows() -> None:
    rows = _unmarked_template_report_rows(
        {
            "result": {
                "marker_detection": {
                    "had_markers": False,
                    "library_match": {
                        "name": "complete_contract_template_GPO.docx",
                        "score": 0.31,
                    },
                }
            }
        }
    )
    joined = " ".join(cell for row in rows for cell in row)
    assert "Unmarked" in joined
    assert "extra time to understand the document" in joined
    assert "complete_contract_template_GPO.docx" in joined
    assert _unmarked_template_report_rows({"result": {"marker_detection": {"had_markers": True}}}) == []
