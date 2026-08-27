"""Application settings: Dynaconf loads ``.env``, Pydantic ``BaseSettings`` reads env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ip_api.core.dynaconf_loader import apply_dynaconf_from_env_files

apply_dynaconf_from_env_files()


def force_sqlite_from_env() -> bool:
    """Launcher sets IPP_FORCE_SQLITE=1 so child dotenv cannot reopen Azure SQL."""
    return (os.getenv("IPP_FORCE_SQLITE") or "").strip().lower() in {"1", "true", "yes", "on"}


def _has_blob_creds(
    connection_string: str | None,
    account_name: str | None,
    account_key: str | None,
    sas_token: str | None,
    sas_url: str | None,
) -> bool:
    return bool(
        (connection_string or "").strip()
        or ((account_name or "").strip() and (account_key or "").strip())
        or ((account_name or "").strip() and (sas_token or "").strip())
        or (sas_url or "").strip()
    )


class Settings(BaseSettings):
    """Central config — same env names as Azure App Settings and ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        env_ignore_empty=True,
        case_sensitive=False,
    )

    storage_base_path: Path = Field(default=Path("./data/storage"))
    jobs_subdirectory: str = "jobs"
    audio_subdirectory: str = "audio"
    templates_subdirectory: str = "templates"
    sqlite_database_path: Path = Field(default=Path("./data/app.db"))

    sqlalchemy_database_url: str | None = None
    azure_sql_server: str | None = None
    azure_sql_user: str = Field(
        default="adminsql",
        validation_alias=AliasChoices("AZURE_SQL_USER", "AZURE_SQL_ADMIN"),
    )
    azure_sql_password: str | None = None
    azure_sql_database: str = "ipp-app-db"
    azure_sql_dialect: str = "pyodbc"
    azure_sql_odbc_driver: str = "ODBC Driver 18 for SQL Server"

    file_storage_backend: str = Field(
        default="",
        validation_alias=AliasChoices("FILE_STORAGE_BACKEND", "STORAGE_BACKEND"),
    )
    azure_storage_connection_string: str | None = None
    azure_storage_account_name: str | None = None
    azure_storage_account_key: str | None = None
    azure_storage_sas_token: str | None = None
    azure_storage_sas_url: str | None = None
    azure_blob_container: str = "docuploadsolution"
    azure_blob_prefix: str = "jobs"
    azure_blob_template_prefix: str = "templates"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://127.0.0.1:8000"
    max_upload_mb: int = 25
    job_ttl_hours: int = 24
    document_max_retries: int = Field(
        default=1,
        validation_alias=AliasChoices("DOCUMENT_MAX_RETRIES", "MAX_RETRIES"),
    )
    document_validation_threshold: float = Field(
        default=0.7,
        validation_alias=AliasChoices(
            "DOCUMENT_VALIDATION_THRESHOLD",
            "DOCUMENT_ACCURACY_THRESHOLD",
            "VALIDATION_THRESHOLD",
        ),
    )
    document_llm_optimization_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DOCUMENT_LLM_OPTIMIZATION_ENABLED",
            "DOCUMENT_LLM_ROUTING_ENABLED",
        ),
    )
    admin_api_key: str | None = None
    gradio_host: str = "127.0.0.1"
    gradio_port: int = 7860
    speech_provider: str = "groq"
    openai_whisper_model: str = "whisper-1"
    groq_whisper_model: str = "whisper-large-v3"

    @field_validator("document_max_retries", mode="after")
    @classmethod
    def _clamp_retries(cls, value: int) -> int:
        return max(0, min(3, value))

    @field_validator("document_validation_threshold", mode="after")
    @classmethod
    def _clamp_threshold(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

    @field_validator("azure_sql_dialect", "speech_provider", "file_storage_backend", mode="after")
    @classmethod
    def _lower_str(cls, value: str) -> str:
        return (value or "").strip().lower()

    @model_validator(mode="after")
    def _normalize_storage(self) -> Self:
        storage = self.storage_base_path.expanduser().resolve()
        if (os.getenv("SQLITE_DATABASE_PATH") or "").strip():
            sqlite_path = Path(self.sqlite_database_path).expanduser().resolve()
        else:
            sqlite_path = (storage.parent / "app.db").resolve()

        backend = (self.file_storage_backend or "").strip().lower()
        if backend in {"azure", "blob", "azureblob"}:
            backend = "azure_blob"
        force_sqlite = force_sqlite_from_env()
        if force_sqlite:
            backend = "local"
        elif not backend:
            backend = (
                "azure_blob"
                if _has_blob_creds(
                    self.azure_storage_connection_string,
                    self.azure_storage_account_name,
                    self.azure_storage_account_key,
                    self.azure_storage_sas_token,
                    self.azure_storage_sas_url,
                )
                else "local"
            )

        object.__setattr__(self, "storage_base_path", storage)
        object.__setattr__(self, "sqlite_database_path", sqlite_path)
        object.__setattr__(self, "file_storage_backend", backend)
        if force_sqlite:
            object.__setattr__(self, "sqlalchemy_database_url", None)
            object.__setattr__(self, "azure_sql_server", None)
            object.__setattr__(self, "azure_sql_password", None)
        return self

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

    @property
    def templates_root(self) -> Path:
        """Local customer template library: ``{base}/templates/{customer}/{template}``."""
        return self.storage_base_path / self.templates_subdirectory

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_root / job_id

    def ensure_directories(self) -> None:
        self.storage_base_path.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.audio_root.mkdir(parents=True, exist_ok=True)
        self.templates_root.mkdir(parents=True, exist_ok=True)
        if not self.uses_azure_sql:
            self.sqlite_database_path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = get_settings()
        _settings.ensure_directories()
    return _settings


def reload_settings() -> Settings:
    """Re-read process env (tests / launcher). Does not re-apply ``.env`` files."""
    global _settings
    _settings = None
    try:
        from ip_api.storage.db import reset_engines

        reset_engines()
    except Exception:  # noqa: BLE001
        pass
    try:
        from ip_api.storage.blob_store import reset_blob_store

        reset_blob_store()
    except Exception:  # noqa: BLE001
        pass
    try:
        from ip_api.storage.session_store import reset_session_store

        reset_session_store()
    except Exception:  # noqa: BLE001
        pass
    try:
        from ip_api.storage.template_store import reset_template_store

        reset_template_store()
    except Exception:  # noqa: BLE001
        pass
    try:
        from ip_api.api.dependencies import reset_app_context

        reset_app_context()
    except Exception:  # noqa: BLE001
        pass
    return settings()
