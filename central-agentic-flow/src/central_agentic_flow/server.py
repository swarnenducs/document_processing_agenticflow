"""Standalone MAF (Microsoft Agent Framework) HTTP service.

Deployable separately from FastAPI. Default: http://127.0.0.1:8003
Routes: GET /health, POST /ask, GET /ask/health, POST /invoke, GET /tools, GET /mcps
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from central_agentic_flow.core.context import ApplicationContext, build_application_context
from central_agentic_flow.core.dependencies import get_app_context, set_app_context


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


class InvokeRequest(BaseModel):
    server: str | None = Field(
        default=None,
        description="Registry name (document, voice, or extra). Optional if tool is prefixed.",
    )
    tool: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    xid: str | None = None


AppContextDep = Annotated[ApplicationContext, Depends(get_app_context)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_dotenv()
    set_app_context(build_application_context())
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Document Processing MAF Orchestrator",
        description="Microsoft Agent Framework — sole caller of MCP servers (document, voice, extras)",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health(_ctx: AppContextDep) -> dict[str, Any]:
        return {"ok": True, "service": "maf"}

    @app.get("/ask/health")
    async def ask_health(_ctx: AppContextDep) -> dict[str, Any]:
        try:
            from central_agentic_flow.mcp_bridge import catalog_mcp_servers
            from central_agentic_flow.orchestrator import resolve_maf_chat_client

            client = resolve_maf_chat_client()
            catalog = await catalog_mcp_servers()
            return {
                "ok": True,
                "orchestrator": "maf",
                "service": "maf",
                "chat_client": type(client).__name__,
                **catalog,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "orchestrator": "maf", "service": "maf", "error": str(exc)}

    @app.get("/mcps")
    async def list_mcps(_ctx: AppContextDep) -> dict[str, Any]:
        from central_agentic_flow.mcp_bridge import catalog_mcp_servers

        try:
            return await catalog_mcp_servers()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"MCP catalog failed: {exc}") from exc

    @app.get("/tools")
    async def list_tools(_ctx: AppContextDep) -> dict[str, Any]:
        from central_agentic_flow.mcp_bridge import catalog_mcp_servers

        try:
            return await catalog_mcp_servers()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"MCP catalog failed: {exc}") from exc

    @app.post("/invoke")
    async def invoke(body: InvokeRequest, _ctx: AppContextDep) -> dict[str, Any]:
        from central_agentic_flow.mcp_bridge import invoke_mcp_tool

        try:
            return await invoke_mcp_tool(
                server=body.server,
                tool=body.tool,
                arguments=body.arguments,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"MCP invoke failed: {exc}") from exc

    @app.post("/ask", response_model=AskResponse)
    async def ask(body: AskRequest, _ctx: AppContextDep) -> AskResponse:
        from central_agentic_flow.orchestrator import ask_maf
        from central_agentic_flow.flow_debug import flow_breakpoint

        flow_breakpoint("maf_http_ask", message=body.message, session_id=body.session_id)
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
