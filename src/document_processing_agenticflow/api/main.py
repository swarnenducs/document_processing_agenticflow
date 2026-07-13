"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from document_processing_agenticflow.api.routes import router
from document_processing_agenticflow.core.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_dotenv()
    cfg = settings()
    cfg.ensure_directories()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Document Processing Agentic Flow API",
        description=(
            "Upload Word templates + JSON data → LangGraph generates styled documents. "
            "Separate LLM mapper (OpenAI) and validator (Groq). "
            "Voice/audio → text via speech-to-text API."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
