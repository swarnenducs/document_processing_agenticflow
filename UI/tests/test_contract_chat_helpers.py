"""UI confirmation helpers (no voice MCP import)."""

from __future__ import annotations

from ui_app.ui.gradio_app import _format_contract_ref, _is_confirmation


def test_is_confirmation_yes() -> None:
    assert _is_confirmation("yes")
    assert _is_confirmation("OK")
    assert not _is_confirmation("CR-1001")


def test_format_contract_ref() -> None:
    assert _format_contract_ref("CR 1001") == "CR-1001"
