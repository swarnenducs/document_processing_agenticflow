#!/usr/bin/env python3
"""Start Gradio UI only (HTTP :7860 by default)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from ui_app.ui.gradio_app import main as server_main

    server_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
