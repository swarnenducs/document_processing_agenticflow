"""central_agent_endpoint resolution: new name wins, old names stay aliases."""

from __future__ import annotations


def _clear_maf_urls(monkeypatch) -> None:
    for key in ("CENTRAL_AGENT_END_POINT", "MAF_BASE_URL", "MAF_URL"):
        monkeypatch.delenv(key, raising=False)


def test_central_agent_end_point_wins_over_maf_base_url(monkeypatch) -> None:
    monkeypatch.setenv("CENTRAL_AGENT_END_POINT", "https://maf-preferred.example.net/")
    monkeypatch.setenv("MAF_BASE_URL", "http://127.0.0.1:8003")
    monkeypatch.setenv("MAF_URL", "http://ignored.example.net")

    from ip_api.services.maf_client import central_agent_endpoint, maf_base_url

    assert central_agent_endpoint() == "https://maf-preferred.example.net"
    assert maf_base_url() == central_agent_endpoint()


def test_maf_base_url_wins_over_maf_url(monkeypatch) -> None:
    _clear_maf_urls(monkeypatch)
    monkeypatch.setenv("MAF_BASE_URL", "http://127.0.0.1:9003/")
    monkeypatch.setenv("MAF_URL", "http://ignored.example.net")

    from ip_api.services.maf_client import central_agent_endpoint

    assert central_agent_endpoint() == "http://127.0.0.1:9003"


def test_maf_url_used_when_preferred_unset(monkeypatch) -> None:
    _clear_maf_urls(monkeypatch)
    monkeypatch.setenv("MAF_URL", "http://127.0.0.1:8003")

    from ip_api.services.maf_client import central_agent_endpoint

    assert central_agent_endpoint() == "http://127.0.0.1:8003"


def test_central_agent_endpoint_local_default(monkeypatch) -> None:
    _clear_maf_urls(monkeypatch)

    from ip_api.services.maf_client import central_agent_endpoint

    assert central_agent_endpoint() == "http://127.0.0.1:8003"
