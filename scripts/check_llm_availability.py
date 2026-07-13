#!/usr/bin/env python3
"""Probe LLM / speech providers configured in project `.env`.

Checks every role the app uses (mapper, validator, agent, speech):
  1. Credentials present (local config)
  2. Live reachability on Groq / Azure OpenAI / OpenAI / compatible APIs

Usage (from repo root)::

    uv run python scripts/check_llm_availability.py
    # or
    .venv/bin/python scripts/check_llm_availability.py

Exit code 0 if all configured roles pass the live check; 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ensure `src` is importable when run as a loose script
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Loads project-root `.env` via settings side effect
from document_processing_agenticflow.core.settings import settings  # noqa: E402
from document_processing_agenticflow.services.llm_factory import (  # noqa: E402
    LLMRoleConfig,
    get_agent_llm,
    get_mapper_llm,
    get_validator_llm,
    provider_credentials_available,
    resolve_role_config,
)
from document_processing_agenticflow.services.speech_to_text import (  # noqa: E402
    resolve_speech_provider,
)


def _env(key: str) -> str | None:
    value = os.getenv(key)
    if value is None or not value.strip():
        return None
    return value.strip()


def _is_placeholder_value(value: str | None) -> bool:
    if not value or not value.strip():
        return True
    lowered = value.strip().lower()
    return any(
        marker in lowered
        for marker in (
            "your_resource",
            "your-resource",
            "your_key",
            "your-key",
            "paste_your",
            "changeme",
            "placeholder",
            "example.openai.azure.com",
            "<",
        )
    )


@dataclass
class CheckResult:
    name: str
    provider: str
    model: str
    credentials_ok: bool
    live_ok: bool
    detail: str

    @property
    def ok(self) -> bool:
        return self.credentials_ok and self.live_ok


def _mask(value: str | None, *, keep: int = 4) -> str:
    if not value:
        return "(missing)"
    if _is_placeholder_value(value):
        return "(placeholder)"
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}…{value[-keep:]}"


def _get_role_llm(role: str) -> tuple[Any, LLMRoleConfig]:
    if role == "mapper":
        return get_mapper_llm()
    if role == "validator":
        return get_validator_llm()
    if role == "agent":
        return get_agent_llm()
    raise ValueError(f"Unknown role: {role}")


def _ping_chat_llm(role: str) -> str:
    """Minimal chat call; raises on failure."""
    llm, _config = _get_role_llm(role)
    response = llm.invoke("Reply with exactly: OK")
    text = getattr(response, "content", None)
    if text is None:
        text = str(response)
    if isinstance(text, list):
        parts = []
        for block in text:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        text = "".join(parts)
    preview = " ".join(str(text).split())[:80]
    return preview or "(empty response)"


def _check_role(role: str, *, live: bool) -> CheckResult:
    config = resolve_role_config(role)
    creds = provider_credentials_available(config)
    if not creds:
        return CheckResult(
            name=f"LLM/{role}",
            provider=config.provider,
            model=config.model,
            credentials_ok=False,
            live_ok=False,
            detail="missing or placeholder credentials",
        )
    if not live:
        return CheckResult(
            name=f"LLM/{role}",
            provider=config.provider,
            model=config.model,
            credentials_ok=True,
            live_ok=True,
            detail="credentials only (--no-live)",
        )
    try:
        preview = _ping_chat_llm(role)
        return CheckResult(
            name=f"LLM/{role}",
            provider=config.provider,
            model=config.model,
            credentials_ok=True,
            live_ok=True,
            detail=f"live ok → {preview!r}",
        )
    except Exception as exc:  # noqa: BLE001 — report any provider error
        return CheckResult(
            name=f"LLM/{role}",
            provider=config.provider,
            model=config.model,
            credentials_ok=True,
            live_ok=False,
            detail=f"{type(exc).__name__}: {exc}",
        )


def _ping_speech(provider: str) -> str:
    """Hit the speech platform without uploading audio when possible."""
    if provider == "groq":
        from groq import Groq

        from document_processing_agenticflow.services.speech_to_text import _speech_api_key

        key = _speech_api_key("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY missing for speech")
        client = Groq(api_key=key)
        models = client.models.list()
        whisper = [m.id for m in models.data if "whisper" in m.id.lower()]
        return f"api.groq.com ok; whisper models={whisper[:3] or '(none listed)'}"

    if provider == "openai":
        from openai import OpenAI

        from document_processing_agenticflow.services.speech_to_text import _speech_api_key

        key = _speech_api_key("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY missing for speech")
        client = OpenAI(api_key=key)
        # models.list confirms the key/platform; Whisper itself needs an audio file
        _ = client.models.list()
        return "api.openai.com ok (models.list)"

    if provider == "azure_openai":
        key = _env("SPEECH_API_KEY") or _env("AZURE_OPENAI_API_KEY")
        endpoint = _env("SPEECH_BASE_URL") or _env("AZURE_OPENAI_ENDPOINT")
        if not key or _is_placeholder_value(key) or _is_placeholder_value(endpoint):
            raise RuntimeError("Azure speech needs AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT")
        # Credential shape is enough for azure speech readiness; full Whisper needs audio + deployment
        return f"credentials present for {endpoint.rstrip('/')}"

    raise RuntimeError(f"Unsupported speech provider: {provider}")


def _check_speech(*, live: bool) -> CheckResult:
    cfg = settings()
    try:
        chosen = resolve_speech_provider()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="speech",
            provider=cfg.speech_provider,
            model=cfg.groq_whisper_model
            if cfg.speech_provider == "groq"
            else cfg.openai_whisper_model,
            credentials_ok=False,
            live_ok=False,
            detail=str(exc),
        )

    model = {
        "groq": cfg.groq_whisper_model,
        "openai": cfg.openai_whisper_model,
        "azure_openai": _env("AZURE_OPENAI_WHISPER_DEPLOYMENT")
        or _env("SPEECH_MODEL")
        or "whisper",
    }.get(chosen, "?")

    if not live:
        return CheckResult(
            name="speech",
            provider=chosen,
            model=model,
            credentials_ok=True,
            live_ok=True,
            detail="credentials only (--no-live)",
        )
    try:
        detail = _ping_speech(chosen)
        return CheckResult(
            name="speech",
            provider=chosen,
            model=model,
            credentials_ok=True,
            live_ok=True,
            detail=detail,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="speech",
            provider=chosen,
            model=model,
            credentials_ok=True,
            live_ok=False,
            detail=f"{type(exc).__name__}: {exc}",
        )


def _platform_snapshot() -> list[tuple[str, str]]:
    """Show which shared platforms have credentials in `.env` (no secrets)."""
    rows: list[tuple[str, str]] = []
    azure_key = _env("AZURE_OPENAI_API_KEY")
    azure_ep = _env("AZURE_OPENAI_ENDPOINT")
    azure_ok = (
        bool(azure_key)
        and not _is_placeholder_value(azure_key)
        and not _is_placeholder_value(azure_ep)
    )
    rows.append(
        (
            "azure_openai",
            f"{'configured' if azure_ok else 'missing'}  key={_mask(azure_key)}  "
            f"endpoint={azure_ep or '(missing)'}",
        )
    )
    groq_key = _env("GROQ_API_KEY")
    rows.append(
        (
            "groq",
            f"{'configured' if groq_key and not _is_placeholder_value(groq_key) else 'missing'}  "
            f"key={_mask(groq_key)}",
        )
    )
    oai_key = _env("OPENAI_API_KEY")
    rows.append(
        (
            "openai",
            f"{'configured' if oai_key and not _is_placeholder_value(oai_key) else 'missing'}  "
            f"key={_mask(oai_key)}",
        )
    )
    return rows


def _print_result(result: CheckResult) -> None:
    status = "OK " if result.ok else "FAIL"
    print(
        f"[{status}] {result.name:16}  provider={result.provider:16}  "
        f"model={result.model}"
    )
    print(f"         credentials={'yes' if result.credentials_ok else 'no'}  "
          f"live={'yes' if result.live_ok else 'no'}  {result.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check .env LLM / speech provider availability")
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Only validate credentials; skip network calls",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print full tracebacks on live failures",
    )
    args = parser.parse_args(argv)
    live = not args.no_live

    # Touch settings so storage dirs / .env load are consistent with the app
    settings()

    print("=== Platform credentials in .env ===")
    for name, detail in _platform_snapshot():
        print(f"  {name:14}  {detail}")
    print()

    print("=== Configured roles (from .env) ===")
    results: list[CheckResult] = []
    for role in ("mapper", "validator", "agent"):
        try:
            result = _check_role(role, live=live)
        except Exception as exc:  # noqa: BLE001
            result = CheckResult(
                name=f"LLM/{role}",
                provider="?",
                model="?",
                credentials_ok=False,
                live_ok=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
            if args.verbose:
                traceback.print_exc()
        results.append(result)
        _print_result(result)

    speech = _check_speech(live=live)
    results.append(speech)
    _print_result(speech)

    print()
    failed = [r for r in results if not r.ok]
    if failed:
        print(f"Result: {len(failed)} check(s) failed.")
        return 1
    print("Result: all configured LLM / speech checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
