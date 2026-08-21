"""FastMCP Depends factories for voice MCP tools.

Use ``from fastmcp.dependencies import Depends`` on tool methods.
Do not import FastAPI ``Depends``.
"""

from __future__ import annotations

from typing import Optional

from voice_enable_mcp.core.context import ApplicationContext, build_application_context
from voice_enable_mcp.core.settings import Settings, settings as load_settings
from voice_enable_mcp.storage.job_store import JobStore

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


def get_settings() -> Settings:
    return load_settings()


def get_job_store() -> JobStore:
    return get_app_context().job_store
