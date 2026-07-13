"""Voice / audio → natural language text (speech-to-text)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from document_processing_agenticflow.core.settings import settings


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    model: str
    language: str | None = None


def _transcribe_openai(audio_path: Path, language: str | None = None) -> TranscriptionResult:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI speech-to-text")

    from openai import OpenAI

    cfg = settings()
    client = OpenAI(api_key=api_key)
    model = cfg.openai_whisper_model

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


def _transcribe_groq(audio_path: Path, language: str | None = None) -> TranscriptionResult:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for Groq speech-to-text")

    from groq import Groq

    cfg = settings()
    client = Groq(api_key=api_key)
    model = cfg.groq_whisper_model

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


def transcribe_audio(
    audio_path: str | Path,
    *,
    language: str | None = None,
    provider: str | None = None,
) -> TranscriptionResult:
    """
    Convert voice/audio to natural language text.

    Provider from SPEECH_PROVIDER env (openai | groq) unless overridden.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    cfg = settings()
    chosen = (provider or cfg.speech_provider).lower()

    if chosen == "groq":
        return _transcribe_groq(path, language=language)
    if chosen == "openai":
        return _transcribe_openai(path, language=language)
    raise ValueError(f"Unsupported SPEECH_PROVIDER: {chosen}. Use openai or groq.")
