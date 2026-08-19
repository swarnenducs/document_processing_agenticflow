"""Optional flow breakpoints for local debugging.

Inactive unless you set env vars (normal `python run_all_components.py` is unchanged).

Enable every marked hop:
  export DEBUG_FLOW=1

Enable named hops only (comma-separated):
  export DEBUG_FLOW_POINTS=create_document_job,map_fields_node,ask_maf
"""

from __future__ import annotations

import os


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def flow_points() -> set[str]:
    raw = os.getenv("DEBUG_FLOW_POINTS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def flow_breakpoint(name: str, **watch: object) -> None:
    """Pause in the debugger when DEBUG_FLOW or DEBUG_FLOW_POINTS matches ``name``."""
    points = flow_points()
    if not (_truthy(os.getenv("DEBUG_FLOW")) or name in points or "*" in points):
        return
    keys = ", ".join(f"{k}={type(v).__name__}" for k, v in watch.items())
    suffix = f" ({keys})" if keys else ""
    print(f"[FLOW_DEBUG] {name}{suffix}", flush=True)
    breakpoint()
