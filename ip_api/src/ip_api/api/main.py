"""FastAPI application entrypoint."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ip_api.api.admin_routes import router as admin_router
from ip_api.api.ask_routes import router as ask_router
from ip_api.api.mcp_routes import router as mcp_router
from ip_api.api.routes import router
from ip_api.core.request_context import (
    SESSION_HEADER,
    USER_EMAIL_HEADER,
    USER_ID_HEADER,
    XID_HEADER,
    XID_HEADER_ALT,
    get_session_id,
    new_xid,
    reset_session_id,
    reset_user_email,
    reset_user_id,
    reset_xid,
    set_session_id,
    set_user_email,
    set_user_id,
    set_xid,
)
from ip_api.services.trace_log import log_event


class XidMiddleware(BaseHTTPMiddleware):
    """Attach xid + optional session/user headers; echo session on response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = (
            request.headers.get(XID_HEADER)
            or request.headers.get(XID_HEADER_ALT)
            or request.headers.get("x-request-id")
            or request.headers.get("x-correlation-id")
        )
        xid = (incoming or "").strip() or new_xid()
        xid_token = set_xid(xid)

        sid_raw = (request.headers.get(SESSION_HEADER) or "").strip() or None
        uid_raw = (request.headers.get(USER_ID_HEADER) or "").strip() or None
        email_raw = (request.headers.get(USER_EMAIL_HEADER) or "").strip() or None
        sid_token = set_session_id(sid_raw)
        uid_token = set_user_id(uid_raw)
        email_token = set_user_email(email_raw)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[XID_HEADER] = xid
            response.headers[XID_HEADER_ALT] = xid
            out_sid = get_session_id()
            if out_sid:
                response.headers[SESSION_HEADER] = out_sid
            if uid_raw:
                response.headers[USER_ID_HEADER] = uid_raw
            if email_raw:
                response.headers[USER_EMAIL_HEADER] = email_raw
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
                    "session_id": get_session_id(),
                    "user_id": uid_raw,
                },
                response_payload={"status_code": status_code},
                status="ok" if status_code < 400 else "error",
                latency_ms=latency,
                xid=xid,
                meta={"path": request.url.path, "session_id": get_session_id()},
            )
            reset_user_email(email_token)
            reset_user_id(uid_token)
            reset_session_id(sid_token)
            reset_xid(xid_token)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_dotenv()
    from ip_api.api.dependencies import set_app_context
    from ip_api.core.context import build_application_context

    context = build_application_context()
    set_app_context(context)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Document Processing Agentic Flow API",
        description=(
            "Upload Word templates + JSON data → LangGraph generates styled documents. "
            "FastAPI can also call class-based FastMCP document and voice agents. "
            "POST /api/ask proxies to the MAF service (:8003 by default), which calls "
            "those MCP tools. Document / voice / MAF calls accept session_id + "
            "user_id / user_email (SQLite-backed)."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(XidMiddleware)
    app.include_router(router, prefix="/api/v1")
    app.include_router(mcp_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(ask_router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, object]:
        return {"ok": True, "health": "/api/v1/health", "docs": "/docs"}

    return app


app = create_app()
