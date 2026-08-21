"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# core/ → package → src → <component folder>
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PACKAGE_ROOT / ".env")
_monorepo = _PACKAGE_ROOT.parent
if (_monorepo / "run_all_components.py").is_file():
    load_dotenv(_monorepo / ".env", override=False)
load_dotenv(override=False)


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

    # SQLite fallback when Azure SQL is not configured
    sqlite_database_path: Path

    # SQLAlchemy / Azure SQL (same tables as ip_api)
    sqlalchemy_database_url: str | None
    azure_sql_server: str | None
    azure_sql_user: str
    azure_sql_password: str | None
    azure_sql_database: str
    azure_sql_dialect: str
    azure_sql_odbc_driver: str

    # Azure Blob (template, JSON, generated .docx)
    file_storage_backend: str  # local | azure_blob
    azure_storage_connection_string: str | None
    azure_storage_account_name: str | None
    azure_storage_account_key: str | None
    azure_storage_sas_token: str | None
    azure_storage_sas_url: str | None
    azure_blob_container: str
    azure_blob_prefix: str

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
    speech_provider: str  # auto | openai | groq
    openai_whisper_model: str
    groq_whisper_model: str

    @property
    def uses_azure_sql(self) -> bool:
        return bool(self.sqlalchemy_database_url) or bool(
            self.azure_sql_server and self.azure_sql_password
        )

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
        if not self.uses_azure_sql:
            self.sqlite_database_path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    storage_base = _path_from_env("STORAGE_BASE_PATH", "./data/storage")
    sqlite_default = str(storage_base.parent / "app.db")
    blob_backend = (os.getenv("FILE_STORAGE_BACKEND") or os.getenv("STORAGE_BACKEND") or "").strip().lower()
    if blob_backend in {"azure", "blob", "azureblob"}:
        blob_backend = "azure_blob"
    has_blob_creds = bool(
        (os.getenv("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
        or (
            (os.getenv("AZURE_STORAGE_ACCOUNT_NAME") or "").strip()
            and (os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or "").strip()
        )
        or (
            (os.getenv("AZURE_STORAGE_ACCOUNT_NAME") or "").strip()
            and (os.getenv("AZURE_STORAGE_SAS_TOKEN") or "").strip()
        )
        or (os.getenv("AZURE_STORAGE_SAS_URL") or "").strip()
    )
    if not blob_backend:
        blob_backend = "azure_blob" if has_blob_creds else "local"
    return Settings(
        storage_base_path=storage_base,
        jobs_subdirectory=os.getenv("JOBS_SUBDIRECTORY", "jobs"),
        audio_subdirectory=os.getenv("AUDIO_SUBDIRECTORY", "audio"),
        sqlite_database_path=_path_from_env("SQLITE_DATABASE_PATH", sqlite_default),
        sqlalchemy_database_url=(os.getenv("SQLALCHEMY_DATABASE_URL") or "").strip() or None,
        azure_sql_server=(os.getenv("AZURE_SQL_SERVER") or "").strip() or None,
        azure_sql_user=(os.getenv("AZURE_SQL_USER") or os.getenv("AZURE_SQL_ADMIN") or "adminsql").strip(),
        azure_sql_password=(os.getenv("AZURE_SQL_PASSWORD") or "").strip() or None,
        azure_sql_database=(os.getenv("AZURE_SQL_DATABASE") or "ipp-app-db").strip(),
        azure_sql_dialect=(os.getenv("AZURE_SQL_DIALECT") or "pyodbc").strip().lower(),
        azure_sql_odbc_driver=os.getenv("AZURE_SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
        file_storage_backend=blob_backend,
        azure_storage_connection_string=(os.getenv("AZURE_STORAGE_CONNECTION_STRING") or "").strip() or None,
        azure_storage_account_name=(os.getenv("AZURE_STORAGE_ACCOUNT_NAME") or "").strip() or None,
        azure_storage_account_key=(os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or "").strip() or None,
        azure_storage_sas_token=(os.getenv("AZURE_STORAGE_SAS_TOKEN") or "").strip() or None,
        azure_storage_sas_url=(os.getenv("AZURE_STORAGE_SAS_URL") or "").strip() or None,
        azure_blob_container=(os.getenv("AZURE_BLOB_CONTAINER") or "docuploadsolution").strip(),
        azure_blob_prefix=(os.getenv("AZURE_BLOB_PREFIX") or "jobs").strip(),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        api_base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        job_ttl_hours=int(os.getenv("JOB_TTL_HOURS", "24")),
        gradio_host=os.getenv("GRADIO_HOST", "127.0.0.1"),
        gradio_port=int(os.getenv("GRADIO_PORT", "7860")),
        speech_provider=os.getenv("SPEECH_PROVIDER", "groq").lower(),
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


def reload_settings() -> Settings:
    """Re-read env (useful in tests)."""
    global _settings
    _settings = None
    try:
        from document_processing_mcp.storage.db import reset_engines

        reset_engines()
    except Exception:  # noqa: BLE001
        pass
    try:
        from document_processing_mcp.storage.blob_store import reset_blob_store

        reset_blob_store()
    except Exception:  # noqa: BLE001
        pass
    try:
        from document_processing_mcp.core.dependencies import reset_app_context

        reset_app_context()
    except Exception:  # noqa: BLE001
        pass
    return settings()
