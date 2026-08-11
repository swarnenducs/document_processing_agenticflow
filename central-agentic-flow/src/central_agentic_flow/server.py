"""Standalone MAF (Microsoft Agent Framework) HTTP service.

Deployable separately from FastAPI. Default: http://127.0.0.1:8003
Routes: GET /health, POST /ask, GET /ask/health
"""

from __future__ import annotations

import os
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


class AskRequest(BaseModel):
    message: str = Field(..., min_length=1)
    instructions: str | None = None
    session_id: str | None = Field(
        default=None,
        description="Client/API session id (echoed; SQLite ownership is in ip_api)",
    )
    user_id: str | None = None
    user_email: str | None = None


class AskResponse(BaseModel):
    ok: bool = True
    text: str
    response_id: str | None = None
    orchestrator: str = "maf"
    service: str = "maf"
    session_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="Document Processing MAF Orchestrator",
        description="Microsoft Agent Framework → document_process_mcp + voice_process_mcp",
        version="0.1.0",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "maf"}

    @app.get("/ask/health")
    async def ask_health() -> dict[str, Any]:
        try:
            from central_agentic_flow.orchestrator import (
                document_mcp_url,
                resolve_maf_chat_client,
                voice_mcp_url,
            )

            client = resolve_maf_chat_client()
            return {
                "ok": True,
                "orchestrator": "maf",
                "service": "maf",
                "chat_client": type(client).__name__,
                "document_mcp_url": document_mcp_url(),
                "voice_mcp_url": voice_mcp_url(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "orchestrator": "maf", "service": "maf", "error": str(exc)}

    @app.post("/ask", response_model=AskResponse)
    async def ask(body: AskRequest) -> AskResponse:
        from central_agentic_flow.orchestrator import ask_maf

        try:
            result = await ask_maf(body.message, instructions=body.instructions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"MAF ask failed: {exc}") from exc
        return AskResponse(
            text=result.text,
            response_id=result.response_id,
            session_id=body.session_id,
            user_id=body.user_id,
            user_email=body.user_email,
        )

    return app


app = create_app()


def main() -> None:
    load_dotenv()
    host = os.getenv("MAF_HOST", "0.0.0.0")
    port = _env_int("MAF_PORT", 8003)
    uvicorn.run(
        "central_agentic_flow.server:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
