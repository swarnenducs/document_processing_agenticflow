"""Shared application context for MAF FastAPI dependency injection."""

from __future__ import annotations

from dataclasses import dataclass

from central_agentic_flow.core.settings import Settings, settings
from central_agentic_flow.storage.call_log_store import CallLogStore
from central_agentic_flow.storage.db import ensure_schema


@dataclass
class ApplicationContext:
    """Process-wide collaborators used by MAF HTTP routes."""

    settings: Settings
    call_log_store: CallLogStore


def build_application_context() -> ApplicationContext:
    cfg = settings()
    cfg.ensure_directories()
    ensure_schema()
    return ApplicationContext(settings=cfg, call_log_store=CallLogStore())
