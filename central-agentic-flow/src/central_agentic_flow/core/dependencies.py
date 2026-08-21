"""Dependency injection functions for MAF FastAPI routes."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends

from central_agentic_flow.core.context import ApplicationContext, build_application_context
from central_agentic_flow.core.settings import Settings, settings as load_settings
from central_agentic_flow.storage.call_log_store import CallLogStore

_app_context: Optional[ApplicationContext] = None


def get_app_context() -> ApplicationContext:
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


def get_call_log_store(
    app_context: ApplicationContext = Depends(get_app_context),
) -> CallLogStore:
    return app_context.call_log_store
