"""Shared application context for voice MCP (no FastAPI Depends)."""

from __future__ import annotations

from dataclasses import dataclass

from voice_enable_mcp.core.settings import Settings, settings
from voice_enable_mcp.storage.job_store import JobStore


@dataclass
class ApplicationContext:
    """Process-wide collaborators used by FastMCP tools."""

    settings: Settings
    job_store: JobStore


def build_application_context() -> ApplicationContext:
    cfg = settings()
    cfg.ensure_directories()
    return ApplicationContext(settings=cfg, job_store=JobStore())
