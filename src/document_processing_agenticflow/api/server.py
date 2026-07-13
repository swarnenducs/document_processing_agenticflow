"""Run the FastAPI server via `uv run doc-api`."""

from __future__ import annotations

import uvicorn

from document_processing_agenticflow.core.settings import settings


def main() -> None:
    cfg = settings()
    uvicorn.run(
        "document_processing_agenticflow.api.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
