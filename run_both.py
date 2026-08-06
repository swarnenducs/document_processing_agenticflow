#!/usr/bin/env python3
"""
Start ALL services: FastAPI + Gradio + document_process_mcp + voice_process_mcp.

MCP servers run in **HTTP** mode by default so FastAPI can call them at:
  - document_process_mcp → http://127.0.0.1:8001/mcp
  - voice_process_mcp    → http://127.0.0.1:8002/mcp

Usage (from project root):
  python run_both.py
  python run_both.py --api-only
  python run_both.py --mcp-only                 # both MCP servers over HTTP
  python run_both.py --mcp-only --mcp-http      # explicit HTTP (same as default)
  python run_both.py --mcp-transport http       # explicit HTTP transport
  python run_both.py --no-mcp
  py -3 run_both.py          # Windows launcher

Env (optional): DOCUMENT_MCP_PORT, VOICE_MCP_PORT, DOCUMENT_MCP_URL, VOICE_MCP_URL,
MCP_TRANSPORT=http

Uses the project ``.venv`` automatically when present (so it works after
``uv sync`` or ``pip install -r requirements.txt`` even if ``uv`` is not on PATH).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def _venv_python() -> Path | None:
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def _reexec_in_venv_if_needed() -> None:
    """If project deps are missing but .venv exists, re-launch with that interpreter."""
    venv_py = _venv_python()
    if venv_py is None:
        return
    try:
        current = Path(sys.executable).resolve()
    except OSError:
        current = Path(sys.executable)
    if current == venv_py.resolve():
        return

    # Probe for a core project dependency (system Python may have httpx but not langgraph).
    try:
        import langgraph  # noqa: F401
    except ImportError:
        os.execv(str(venv_py), [str(venv_py), str(ROOT / "run_both.py"), *sys.argv[1:]])


def _bootstrap() -> None:
    os.chdir(ROOT)
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    existing = os.environ.get("PYTHONPATH", "")
    if str(SRC) not in existing.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            str(SRC) + (os.pathsep + existing if existing else "")
        )


def main() -> int:
    _reexec_in_venv_if_needed()
    _bootstrap()
    try:
        from document_processing_agenticflow.run_app import main as run_main
    except ImportError as exc:
        print(
            "Missing dependencies.\n"
            "Install one of:\n"
            "  uv sync\n"
            "  pip install -r requirements.txt\n"
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 1
    return run_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
