"""Contract text download helper."""

from __future__ import annotations

from ip_api.services.contract_text import render_contract_text


def test_render_contract_text_includes_title() -> None:
    text = render_contract_text({"contractReferenceNumber": "CR-1001", "legalName": "AVC"})
    assert "SUPPLY CONTRACT" in text
    assert "CR-1001" in text
    assert "AVC" in text
