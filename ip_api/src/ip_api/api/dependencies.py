"""Dependency injection functions for FastAPI routes."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends

from ip_api.core.context import ApplicationContext, build_application_context
from ip_api.core.settings import Settings, settings as load_settings
from ip_api.storage.blob_store import BlobStore
from ip_api.storage.job_store import JobStore
from ip_api.storage.session_store import SessionStore
from ip_api.storage.template_store import TemplateStore

_app_context: Optional[ApplicationContext] = None


def get_app_context() -> ApplicationContext:
    """Return the singleton application context.

    Builds it on first use so tests that skip lifespan still work.
    """
    global _app_context
    if _app_context is None:
        _app_context = build_application_context()
    return _app_context


def set_app_context(context: ApplicationContext) -> None:
    global _app_context
    _app_context = context


def reset_app_context() -> None:
    global _app_context
    _app_context = None


def get_settings_dependency() -> Settings:
    return load_settings()


def get_job_store(
    app_context: ApplicationContext = Depends(get_app_context),
) -> JobStore:
    return app_context.job_store


def get_blob_store_dep(
    app_context: ApplicationContext = Depends(get_app_context),
) -> BlobStore:
    return app_context.blob_store


def get_template_store_dep(
    app_context: ApplicationContext = Depends(get_app_context),
) -> TemplateStore:
    return app_context.template_store


def get_session_store_dep(
    app_context: ApplicationContext = Depends(get_app_context),
) -> SessionStore:
    return app_context.session_store
