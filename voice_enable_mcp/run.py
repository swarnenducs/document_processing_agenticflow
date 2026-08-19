#!/usr/bin/env python3
"""Start voice_enable_mcp (HTTP :8002 by default)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from voice_enable_mcp.server import main as server_main

    return int(server_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
