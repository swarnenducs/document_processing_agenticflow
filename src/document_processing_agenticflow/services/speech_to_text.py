"""Voice / audio → natural language text (speech-to-text)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from document_processing_agenticflow.core.settings import settings
from document_processing_agenticflow.services.trace_log import log_event


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    model: str
    language: str | None = None


def _clean_secret(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().strip('"').strip("'")
    return value or None


def _speech_api_key(*env_names: str) -> str | None:
    for name in ("SPEECH_API_KEY", *env_names):
        key = _clean_secret(os.getenv(name))
        if key:
            return key
    return None


def _normalize_provider(name: str) -> str:
    aliases = {
        "azure": "azure_openai",
        "aoai": "azure_openai",
        "azure-openai": "azure_openai",
        "default": "auto",
        "": "auto",
    }
    key = name.strip().lower()
    return aliases.get(key, key)


def _openai_ready() -> bool:
    return bool(_speech_api_key("OPENAI_API_KEY"))


def _groq_ready() -> bool:
    return bool(_speech_api_key("GROQ_API_KEY"))


def _azure_ready() -> bool:
    key = _speech_api_key("AZURE_OPENAI_API_KEY")
    endpoint = _clean_secret(
        os.getenv("SPEECH_BASE_URL") or os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    return bool(key and endpoint)


def _transcribe_openai(audio_path: Path, language: str | None = None) -> TranscriptionResult:
    api_key = _speech_api_key("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Speech (OpenAI) needs OPENAI_API_KEY or SPEECH_API_KEY in project `.env`."
        )

    from openai import OpenAI

    cfg = settings()
    client_kwargs: dict = {"api_key": api_key}
    base_url = _clean_secret(os.getenv("SPEECH_BASE_URL") or os.getenv("OPENAI_BASE_URL"))
    if base_url:
        client_kwargs["base_url"] = base_url.rstrip("/")

    client = OpenAI(**client_kwargs)
    model = _clean_secret(os.getenv("SPEECH_MODEL")) or cfg.openai_whisper_model

    with audio_path.open("rb") as audio_file:
        kwargs: dict = {"model": model, "file": audio_file, "response_format": "text"}
        if language:
            kwargs["language"] = language
        text = client.audio.transcriptions.create(**kwargs)

    if not isinstance(text, str):
        text = str(text)

    return TranscriptionResult(
        text=text.strip(),
        provider="openai",
        model=model,
        language=language,
    )


def _transcribe_azure_openai(
    audio_path: Path, language: str | None = None
) -> TranscriptionResult:
    """Azure OpenAI Whisper deployment via AzureOpenAI client."""
    api_key = _speech_api_key("AZURE_OPENAI_API_KEY")
    endpoint = _clean_secret(
        os.getenv("SPEECH_BASE_URL") or os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    if not api_key or not endpoint:
        raise RuntimeError(
            "Speech (Azure OpenAI) needs AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT "
            "in the project `.env` (or SPEECH_API_KEY + SPEECH_BASE_URL)."
        )

    from openai import AzureOpenAI

    cfg = settings()
    api_version = (
        _clean_secret(os.getenv("SPEECH_API_VERSION"))
        or _clean_secret(os.getenv("AZURE_OPENAI_API_VERSION"))
        or "2024-06-01"
    )
    # For Azure, `model` is the *deployment name* (not whisper-1).
    deployment = (
        _clean_secret(os.getenv("SPEECH_MODEL"))
        or _clean_secret(os.getenv("AZURE_OPENAI_WHISPER_DEPLOYMENT"))
        or _clean_secret(os.getenv("AZURE_OPENAI_DEPLOYMENT"))
        or "whisper"
    )

    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint.rstrip("/"),
    )

    with audio_path.open("rb") as audio_file:
        kwargs: dict = {
            "model": deployment,
            "file": audio_file,
            "response_format": "text",
        }
        if language:
            kwargs["language"] = language
        text = client.audio.transcriptions.create(**kwargs)

    if not isinstance(text, str):
        text = str(text)

    return TranscriptionResult(
        text=text.strip(),
        provider="azure_openai",
        model=deployment,
        language=language,
    )


def _transcribe_groq(audio_path: Path, language: str | None = None) -> TranscriptionResult:
    api_key = _speech_api_key("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Speech (Groq) needs GROQ_API_KEY or SPEECH_API_KEY in project `.env`."
        )

    from groq import Groq

    cfg = settings()
    client = Groq(api_key=api_key)
    model = _clean_secret(os.getenv("SPEECH_MODEL")) or cfg.groq_whisper_model

    with audio_path.open("rb") as audio_file:
        kwargs: dict = {"model": model, "file": audio_file, "response_format": "text"}
        if language:
            kwargs["language"] = language
        text = client.audio.transcriptions.create(**kwargs)

    if not isinstance(text, str):
        text = str(text)

    return TranscriptionResult(
        text=text.strip(),
        provider="groq",
        model=model,
        language=language,
    )


def resolve_speech_provider(provider: str | None = None) -> str:
    """
    Pick a working speech provider: openai | azure_openai | groq.

    ``auto`` prefers Azure when Azure endpoint+key exist, else OpenAI, else Groq.
    """
    cfg = settings()
    raw = _normalize_provider(provider or cfg.speech_provider or "auto")

    if raw == "auto":
        if _azure_ready():
            return "azure_openai"
        if _openai_ready():
            return "openai"
        if _groq_ready():
            return "groq"
        raise RuntimeError(
            "No speech credentials found. For Azure OpenAI add to project `.env`:\n"
            "  SPEECH_PROVIDER=azure_openai\n"
            "  AZURE_OPENAI_API_KEY=...\n"
            "  AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/\n"
            "  AZURE_OPENAI_WHISPER_DEPLOYMENT=whisper\n"
            "  AZURE_OPENAI_API_VERSION=2024-06-01\n"
            "Or use OPENAI_API_KEY / GROQ_API_KEY with SPEECH_PROVIDER=openai|groq|auto"
        )

    if raw == "azure_openai":
        if _azure_ready():
            return "azure_openai"
        raise RuntimeError(
            "Azure speech needs AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT "
            "(and a Whisper deployment name in AZURE_OPENAI_WHISPER_DEPLOYMENT)."
        )

    if raw == "openai":
        if _openai_ready():
            return "openai"
        if _azure_ready():
            return "azure_openai"
        if _groq_ready():
            return "groq"
        raise RuntimeError(
            "OPENAI_API_KEY missing. Set it, or use SPEECH_PROVIDER=azure_openai / groq."
        )

    if raw == "groq":
        if _groq_ready():
            return "groq"
        if _azure_ready():
            return "azure_openai"
        if _openai_ready():
            return "openai"
        raise RuntimeError("GROQ_API_KEY missing. Set it, or use azure_openai / openai.")

    raise ValueError(
        f"Unsupported SPEECH_PROVIDER: {raw}. Use azure_openai, openai, groq, or auto."
    )


def _call_provider(
    chosen: str,
    path: Path,
    language: str | None,
) -> TranscriptionResult:
    if chosen == "groq":
        return _transcribe_groq(path, language=language)
    if chosen == "azure_openai":
        return _transcribe_azure_openai(path, language=language)
    if chosen == "openai":
        return _transcribe_openai(path, language=language)
    raise ValueError(f"Unsupported speech provider: {chosen}")


def _is_connection_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    markers = ("connection", "connect", "timeout", "timed out", "network", "proxy")
    return any(m in name for m in markers) or any(m in text for m in markers)


def _fallback_providers(primary: str) -> list[str]:
    order = ["groq", "openai", "azure_openai"]
    rest = [p for p in order if p != primary]
    ready = {
        "groq": _groq_ready(),
        "openai": _openai_ready(),
        "azure_openai": _azure_ready(),
    }
    return [p for p in rest if ready.get(p)]


def transcribe_audio(
    audio_path: str | Path,
    *,
    language: str | None = None,
    provider: str | None = None,
) -> TranscriptionResult:
    """Convert voice/audio to text. Provider: azure_openai | openai | groq | auto.

    On connection failures, automatically tries other configured providers.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    chosen = resolve_speech_provider(provider)
    errors: list[str] = []
    started = time.perf_counter()
    try:
        result = _call_provider(chosen, path, language)
        log_event(
            kind="speech",
            name="transcribe_audio",
            request_payload={
                "audio_path": str(path),
                "language": language,
                "provider": chosen,
            },
            response_payload={
                "text": result.text,
                "provider": result.provider,
                "model": result.model,
                "language": result.language,
            },
            status="ok",
            latency_ms=(time.perf_counter() - started) * 1000.0,
            provider=result.provider,
            model=result.model,
        )
        return result
    except Exception as primary_exc:  # noqa: BLE001
        errors.append(f"{chosen}: {primary_exc}")
        if not _is_connection_error(primary_exc):
            log_event(
                kind="speech",
                name="transcribe_audio",
                request_payload={
                    "audio_path": str(path),
                    "language": language,
                    "provider": chosen,
                },
                status="error",
                error=str(primary_exc),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                provider=chosen,
            )
            raise

    for alt in _fallback_providers(chosen):
        try:
            result = _call_provider(alt, path, language)
            log_event(
                kind="speech",
                name="transcribe_audio",
                request_payload={
                    "audio_path": str(path),
                    "language": language,
                    "provider": chosen,
                    "fallback": alt,
                },
                response_payload={
                    "text": result.text,
                    "provider": result.provider,
                    "model": result.model,
                    "language": result.language,
                },
                status="ok",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                provider=result.provider,
                model=result.model,
                meta={"errors_before_fallback": errors},
            )
            return result
        except Exception as alt_exc:  # noqa: BLE001
            errors.append(f"{alt}: {alt_exc}")
            continue

    detail = " | ".join(errors)
    log_event(
        kind="speech",
        name="transcribe_audio",
        request_payload={"audio_path": str(path), "language": language, "provider": chosen},
        status="error",
        error=detail,
        latency_ms=(time.perf_counter() - started) * 1000.0,
        provider=chosen,
    )
    raise RuntimeError(
        "Speech transcription connection failed for all available providers. "
        f"Tried: {detail}. "
        "Check network access to Groq/OpenAI, or type the instruction in chat instead."
    )
