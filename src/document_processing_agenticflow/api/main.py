"""FastAPI application entrypoint."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from document_processing_agenticflow.api.mcp_routes import router as mcp_router
from document_processing_agenticflow.api.routes import router
from document_processing_agenticflow.core.request_context import (
    XID_HEADER,
    XID_HEADER_ALT,
    new_xid,
    reset_xid,
    set_xid,
)
from document_processing_agenticflow.core.settings import settings
from document_processing_agenticflow.services.trace_log import log_event


class XidMiddleware(BaseHTTPMiddleware):
    """Attach xid to every request and log HTTP request/response metadata."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = (
            request.headers.get(XID_HEADER)
            or request.headers.get(XID_HEADER_ALT)
            or request.headers.get("x-request-id")
            or request.headers.get("x-correlation-id")
        )
        xid = (incoming or "").strip() or new_xid()
        token = set_xid(xid)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[XID_HEADER] = xid
            response.headers[XID_HEADER_ALT] = xid
            return response
        finally:
            latency = (time.perf_counter() - started) * 1000.0
            log_event(
                kind="http",
                name=f"{request.method} {request.url.path}",
                request_payload={
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "client": request.client.host if request.client else None,
                },
                response_payload={"status_code": status_code},
                status="ok" if status_code < 400 else "error",
                latency_ms=latency,
                xid=xid,
                meta={"path": request.url.path},
            )
            reset_xid(token)


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
            "FastAPI can also call class-based FastMCP document and voice agents. "
            "Every request carries an xid (X-Request-ID) used to track tools + LLM logs."
        ),
        version="0.3.0",
        lifespan=lifespan,
    )
    app.add_middleware(XidMiddleware)
    app.include_router(router, prefix="/api/v1")
    app.include_router(mcp_router, prefix="/api/v1")
    return app


app = create_app()
