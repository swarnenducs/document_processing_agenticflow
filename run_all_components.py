#!/usr/bin/env python3
"""
Start ALL deployable components locally (outside component folders).

  document-processing-mcp (:8001)
  voice_enable_mcp        (:8002)
  central-agentic-flow    (:8003)  ← MAF
  ipp_agentic_api         (:8000)
  UI                      (:7860)

Usage:
  python run_all_components.py
  python run_all_components.py --maf-only
  python run_all_components.py --mcp-only
  uv run --directory . python run_all_components.py

Install:
  uv sync
  # or: pip install -r requirements-dev.txt
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SRC_ROOTS = [
    ROOT / "document-processing-mcp" / "src",
    ROOT / "voice_enable_mcp" / "src",
    ROOT / "central-agentic-flow" / "src",
    ROOT / "ipp_agentic_api" / "src",
    ROOT / "UI" / "src",
]


def _venv_python() -> Path | None:
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def _reexec_in_venv_if_needed() -> None:
    venv_py = _venv_python()
    if venv_py is None:
        return
    try:
        current = Path(sys.executable).resolve()
    except OSError:
        current = Path(sys.executable)
    if current == venv_py.resolve():
        return
    try:
        import httpx  # noqa: F401
    except ImportError:
        os.execv(str(venv_py), [str(venv_py), str(ROOT / "run_all_components.py"), *sys.argv[1:]])


def _bootstrap() -> None:
    os.chdir(ROOT)
    parts = [str(p) for p in SRC_ROOTS if p.is_dir()]
    root = str(ROOT)
    if root not in parts:
        parts.append(root)
    existing = os.environ.get("PYTHONPATH", "")
    for p in existing.split(os.pathsep):
        if p and p not in parts:
            parts.append(p)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)
    if root not in sys.path:
        sys.path.insert(0, root)
    for p in reversed(SRC_ROOTS):
        s = str(p)
        if p.is_dir() and s not in sys.path:
            sys.path.insert(0, s)


def main() -> int:
    _reexec_in_venv_if_needed()
    _bootstrap()
    try:
        from ip_api.run_app import main as run_main
    except ImportError as exc:
        print(
            "Missing dependencies.\n"
            "Install:\n"
            "  uv sync\n"
            "  or: pip install -r requirements-dev.txt\n"
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 1
    return run_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
