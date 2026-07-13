"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _path_from_env(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    return Path(raw).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    """Central config — storage paths and API behaviour."""

    # File storage (blobs: template, output .docx, audio uploads)
    storage_base_path: Path
    jobs_subdirectory: str
    audio_subdirectory: str

    # SQLite database file path (job metadata)
    sqlite_database_path: Path

    # API
    api_host: str
    api_port: int
    api_base_url: str
    max_upload_mb: int
    job_ttl_hours: int

    # Gradio UI
    gradio_host: str
    gradio_port: int

    # Speech-to-text (voice → natural language text)
    speech_provider: str  # openai | groq
    openai_whisper_model: str
    groq_whisper_model: str

    @property
    def jobs_root(self) -> Path:
        return self.storage_base_path / self.jobs_subdirectory

    @property
    def audio_root(self) -> Path:
        return self.storage_base_path / self.audio_subdirectory

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_root / job_id

    def ensure_directories(self) -> None:
        self.storage_base_path.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.audio_root.mkdir(parents=True, exist_ok=True)
        self.sqlite_database_path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    storage_base = _path_from_env("STORAGE_BASE_PATH", "./data/storage")
    sqlite_default = str(storage_base.parent / "app.db")
    return Settings(
        storage_base_path=storage_base,
        jobs_subdirectory=os.getenv("JOBS_SUBDIRECTORY", "jobs"),
        audio_subdirectory=os.getenv("AUDIO_SUBDIRECTORY", "audio"),
        sqlite_database_path=_path_from_env("SQLITE_DATABASE_PATH", sqlite_default),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        api_base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        job_ttl_hours=int(os.getenv("JOB_TTL_HOURS", "24")),
        gradio_host=os.getenv("GRADIO_HOST", "127.0.0.1"),
        gradio_port=int(os.getenv("GRADIO_PORT", "7860")),
        speech_provider=os.getenv("SPEECH_PROVIDER", "openai").lower(),
        openai_whisper_model=os.getenv("OPENAI_WHISPER_MODEL", "whisper-1"),
        groq_whisper_model=os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3"),
    )


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = get_settings()
        _settings.ensure_directories()
    return _settings
