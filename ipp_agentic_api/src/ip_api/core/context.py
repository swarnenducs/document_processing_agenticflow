"""Shared application context for FastAPI dependency injection."""

from __future__ import annotations

from dataclasses import dataclass

from ip_api.core.settings import Settings, settings
from ip_api.storage.blob_store import BlobStore, get_blob_store
from ip_api.storage.db import ensure_schema
from ip_api.storage.job_store import JobStore
from ip_api.storage.session_store import SessionStore, get_session_store
from ip_api.storage.template_store import TemplateStore, get_template_store


@dataclass
class ApplicationContext:
    """Process-wide collaborators used by FastAPI routes."""

    settings: Settings
    job_store: JobStore
    blob_store: BlobStore
    template_store: TemplateStore
    session_store: SessionStore


def build_application_context() -> ApplicationContext:
    cfg = settings()
    cfg.ensure_directories()
    ensure_schema()
    return ApplicationContext(
        settings=cfg,
        job_store=JobStore(),
        blob_store=get_blob_store(),
        template_store=get_template_store(),
        session_store=get_session_store(),
    )
