"""Run the FastAPI server via `uv run doc-api`."""

from __future__ import annotations

import uvicorn

from ip_api.core.settings import settings


def main() -> None:
    cfg = settings()
    uvicorn.run(
        "ip_api.api.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
