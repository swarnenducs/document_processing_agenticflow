"""Start ALL deployable components (`python run_all_components.py` / `uv run doc-all`).

Components (default ports):
  - document_process_mcp  :8001/mcp
  - voice_process_mcp     :8002/mcp
  - MAF orchestrator      :8003
  - FastAPI gateway       :8000  (proxies /api/ask → MAF)
  - Gradio UI             :7860
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # ipp_agentic_api/src/ip_api -> repo root
SRC_ROOTS = [
    PROJECT_ROOT / "document-processing-mcp" / "src",
    PROJECT_ROOT / "voice_enable_mcp" / "src",
    PROJECT_ROOT / "central-agentic-flow" / "src",
    PROJECT_ROOT / "ipp_agentic_api" / "src",
    PROJECT_ROOT / "UI" / "src",
]


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _api_url() -> str:
    base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/health"


def _maf_health_url() -> str:
    from ip_api.services.maf_client import central_agent_endpoint

    return f"{central_agent_endpoint()}/health"


def wait_for_http(
    url: str,
    *,
    name: str,
    timeout: float = 60.0,
    interval: float = 0.5,
    accept_4xx: bool = False,
    request_timeout: float = 15.0,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=request_timeout)
            if resp.status_code == 200 or (accept_4xx and resp.status_code < 500):
                print(f"{name} ready: {url}")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(interval)
    print(f"Timed out waiting for {name} at {url}", file=sys.stderr)
    return False


def wait_for_api(timeout: float = 60.0, interval: float = 0.5) -> bool:
    return wait_for_http(_api_url(), name="API", timeout=timeout, interval=interval)


def wait_for_maf(timeout: float = 30.0, interval: float = 0.4) -> bool:
    return wait_for_http(_maf_health_url(), name="MAF", timeout=timeout, interval=interval)


def wait_for_mcp_http(url: str, *, name: str, timeout: float = 30.0, interval: float = 0.4) -> bool:
    return wait_for_http(url, name=name, timeout=timeout, interval=interval, accept_4xx=True)


def _python_cmd() -> list[str]:
    return [sys.executable]


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    for src in SRC_ROOTS:
        s = str(src)
        if s not in parts:
            parts.insert(0, s)
    root = str(PROJECT_ROOT)
    if root not in parts:
        parts.append(root)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def build_api_command(*, use_uv: bool) -> list[str]:
    if use_uv and shutil.which("uv"):
        return ["uv", "run", "doc-api"]
    return [
        *_python_cmd(),
        "-m",
        "uvicorn",
        "ip_api.api.main:app",
        "--host",
        os.getenv("API_HOST", "0.0.0.0"),
        "--port",
        str(_env_int("API_PORT", 8000)),
    ]


def build_ui_command(*, use_uv: bool) -> list[str]:
    if use_uv and shutil.which("uv"):
        return ["uv", "run", "doc-ui"]
    return [
        *_python_cmd(),
        "-m",
        "ui_app.ui.gradio_app",
    ]


def build_maf_command(*, use_uv: bool) -> list[str]:
    if use_uv and shutil.which("uv"):
        return ["uv", "run", "doc-maf"]
    return [
        *_python_cmd(),
        "-m",
        "central_agentic_flow.server",
    ]


def build_document_mcp_command(*, use_uv: bool, transport: str = "http") -> list[str]:
    host = os.getenv("DOCUMENT_MCP_HOST", "127.0.0.1")
    port = str(_env_int("DOCUMENT_MCP_PORT", 8001))
    if use_uv and shutil.which("uv"):
        base = ["uv", "run", "document-process-mcp"]
    else:
        base = [
            *_python_cmd(),
            "-m",
            "document_processing_mcp.server",
        ]
    cmd = [*base, "--transport", transport]
    if transport == "http":
        cmd.extend(["--host", host, "--port", port])
    return cmd


def build_voice_mcp_command(*, use_uv: bool, transport: str = "http") -> list[str]:
    host = os.getenv("VOICE_MCP_HOST", "127.0.0.1")
    port = str(_env_int("VOICE_MCP_PORT", 8002))
    if use_uv and shutil.which("uv"):
        base = ["uv", "run", "voice-process-mcp"]
    else:
        base = [
            *_python_cmd(),
            "-m",
            "voice_enable_mcp.server",
        ]
    cmd = [*base, "--transport", transport]
    if transport == "http":
        cmd.extend(["--host", host, "--port", port])
    return cmd


def start_process(cmd: list[str], name: str) -> subprocess.Popen:
    print(f"Starting {name}: {' '.join(cmd)}")
    kwargs: dict = {
        "cwd": str(PROJECT_ROOT),
        "env": _child_env(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(cmd, **kwargs)


def terminate_process(proc: subprocess.Popen | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    print(f"Stopping {name} (pid {proc.pid})...")
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            try:
                proc.wait(timeout=3)
                return
            except subprocess.TimeoutExpired:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


# Azure SQL / Blob leftover in .env must not break `python run_all_components.py`.
_AZURE_SQL_ENV_KEYS = (
    "SQLALCHEMY_DATABASE_URL",
    "AZURE_SQL_SERVER",
    "AZURE_SQL_PASSWORD",
)


def _truthy_env(key: str) -> bool:
    return (os.getenv(key) or "").strip().lower() in {"1", "true", "yes", "on"}


def apply_local_storage_for_launcher(*, use_azure_sql: bool, use_azure_blob: bool) -> None:
    """Laptop launcher: SQLite + local files unless Azure backends are opted in.

    Azure Web Apps do not use this script. Children call ``load_dotenv(.env)``,
    so Azure SQL keys must stay in ``os.environ`` as **empty** (not popped) and
    ``IPP_FORCE_SQLITE=1`` must be set; otherwise ``.env`` fills ``ipp-app-db``
    again and MCP crashes with ODBC 4060.
    """
    if use_azure_sql or _truthy_env("IPP_USE_AZURE_SQL"):
        os.environ.pop("IPP_FORCE_SQLITE", None)
        print("Local run: Azure SQL from env (IPP_USE_AZURE_SQL / --azure-sql).")
    else:
        had_sql = any((os.getenv(k) or "").strip() for k in _AZURE_SQL_ENV_KEYS)
        os.environ["IPP_FORCE_SQLITE"] = "1"
        for key in _AZURE_SQL_ENV_KEYS:
            os.environ[key] = ""
        if had_sql:
            print(
                "Local run: using SQLite (ignored Azure SQL in .env, e.g. ipp-app-db). "
                "Pass --azure-sql or set IPP_USE_AZURE_SQL=1 to use Azure SQL."
            )
        else:
            print("Local run: SQLite at SQLITE_DATABASE_PATH (default).")

    if use_azure_blob or _truthy_env("IPP_USE_AZURE_BLOB"):
        print("Local run: Azure Blob from env (IPP_USE_AZURE_BLOB / --azure-blob).")
    else:
        os.environ["FILE_STORAGE_BACKEND"] = "local"
        print("Local run: FILE_STORAGE_BACKEND=local (pass --azure-blob for Blob).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run ALL components: document-mcp + voice-mcp + MAF + FastAPI + Gradio"
        )
    )
    parser.add_argument("--api-only", action="store_true", help="Start FastAPI gateway only")
    parser.add_argument("--ui-only", action="store_true", help="Start Gradio UI only")
    parser.add_argument("--maf-only", action="store_true", help="Start MAF orchestrator only")
    parser.add_argument(
        "--mcp-only",
        action="store_true",
        help="Start document_process_mcp + voice_process_mcp only",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Do not start MCP agents",
    )
    parser.add_argument(
        "--no-maf",
        action="store_true",
        help="Do not start MAF service (API /api/ask needs MAF at CENTRAL_AGENT_END_POINT)",
    )
    parser.add_argument(
        "--mcp-transport",
        choices=["http", "stdio"],
        default=os.getenv("MCP_TRANSPORT", "http"),
        help="MCP transport (default: http)",
    )
    parser.add_argument(
        "--mcp-http",
        action="store_true",
        help="Force MCP HTTP mode",
    )
    parser.add_argument("--no-wait", action="store_true", help="Skip health waits")
    parser.add_argument("--api-timeout", type=float, default=90.0)
    parser.add_argument("--mcp-timeout", type=float, default=30.0)
    parser.add_argument("--maf-timeout", type=float, default=30.0)
    parser.add_argument(
        "--use-uv",
        action="store_true",
        help="Launch children via `uv run` entry points",
    )
    parser.add_argument(
        "--debug-flow",
        action="store_true",
        help="Print file:line method in every child process (DEBUG_FLOW=1)",
    )
    parser.add_argument(
        "--azure-sql",
        action="store_true",
        help="Use Azure SQL from .env (default local launcher uses SQLite)",
    )
    parser.add_argument(
        "--azure-blob",
        action="store_true",
        help="Use Azure Blob from .env (default local launcher uses FILE_STORAGE_BACKEND=local)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args(argv)
    apply_local_storage_for_launcher(
        use_azure_sql=bool(args.azure_sql),
        use_azure_blob=bool(args.azure_blob),
    )
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    if args.azure_sql or _truthy_env("IPP_USE_AZURE_SQL"):
        from scripts.load_sql_password_from_keyvault import apply_sql_password_from_keyvault

        apply_sql_password_from_keyvault()
    if args.debug_flow and not (os.getenv("DEBUG_FLOW") or "").strip():
        os.environ["DEBUG_FLOW"] = "1"
    from ip_api.flow_debug import install_flow_logger

    install_flow_logger()
    use_uv = bool(args.use_uv)
    mcp_transport = "http" if args.mcp_http else str(args.mcp_transport)
    if mcp_transport == "stdio" and not args.mcp_only:
        print(
            "MCP stdio cannot be used with FastAPI/MAF HTTP clients; forcing http.",
            file=sys.stderr,
        )
        mcp_transport = "http"
    os.environ["DOCUMENT_MCP_TRANSPORT"] = mcp_transport
    os.environ["VOICE_MCP_TRANSPORT"] = mcp_transport
    os.environ["MCP_TRANSPORT"] = mcp_transport

    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = _env_int("API_PORT", 8000)
    gradio_host = os.getenv("GRADIO_HOST", "127.0.0.1")
    gradio_port = _env_int("GRADIO_PORT", 7860)
    maf_host = os.getenv("MAF_HOST", "0.0.0.0")
    maf_port = _env_int("MAF_PORT", 8003)
    from ip_api.services.maf_client import central_agent_endpoint

    if not (
        (os.getenv("CENTRAL_AGENT_END_POINT") or "").strip()
        or (os.getenv("MAF_BASE_URL") or "").strip()
        or (os.getenv("MAF_URL") or "").strip()
    ):
        os.environ.setdefault("MAF_BASE_URL", f"http://127.0.0.1:{maf_port}")
    maf_base = central_agent_endpoint()
    os.environ.setdefault("CENTRAL_AGENT_END_POINT", maf_base)
    os.environ.setdefault("MAF_BASE_URL", maf_base)

    doc_mcp_host = os.getenv("DOCUMENT_MCP_HOST", "127.0.0.1")
    doc_mcp_port = _env_int("DOCUMENT_MCP_PORT", 8001)
    voice_mcp_host = os.getenv("VOICE_MCP_HOST", "127.0.0.1")
    voice_mcp_port = _env_int("VOICE_MCP_PORT", 8002)
    doc_mcp_url = os.getenv("DOCUMENT_MCP_URL", f"http://{doc_mcp_host}:{doc_mcp_port}/mcp").rstrip("/")
    voice_mcp_url = os.getenv("VOICE_MCP_URL", f"http://{voice_mcp_host}:{voice_mcp_port}/mcp").rstrip("/")

    procs: dict[str, subprocess.Popen | None] = {
        "api": None,
        "ui": None,
        "maf": None,
        "doc_mcp": None,
        "voice_mcp": None,
    }

    def _shutdown(signum: int | None = None, _frame: object | None = None) -> None:
        del signum, _frame
        terminate_process(procs["ui"], "Gradio UI")
        terminate_process(procs["api"], "FastAPI")
        terminate_process(procs["maf"], "MAF")
        terminate_process(procs["doc_mcp"], "document_process_mcp")
        terminate_process(procs["voice_mcp"], "voice_process_mcp")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        only_flags = sum(
            bool(x) for x in (args.api_only, args.ui_only, args.mcp_only, args.maf_only)
        )
        if only_flags > 1:
            print("Use only one of --api-only / --ui-only / --mcp-only / --maf-only", file=sys.stderr)
            return 2

        start_mcp = not args.no_mcp and not args.ui_only and not args.api_only and not args.maf_only
        if args.mcp_only:
            start_mcp = True
        start_maf = (
            not args.no_maf
            and not args.ui_only
            and not args.mcp_only
            and not args.api_only
        ) or args.maf_only
        # When starting API as part of full stack (or api-only with mcp), also start MCP/MAF unless disabled
        if args.api_only:
            start_mcp = not args.no_mcp
            start_maf = not args.no_maf
        start_api = not args.ui_only and not args.mcp_only and not args.maf_only
        start_ui = not args.api_only and not args.mcp_only and not args.maf_only

        if start_mcp:
            print(f"MCP transport: {mcp_transport}")
            procs["doc_mcp"] = start_process(
                build_document_mcp_command(use_uv=use_uv, transport=mcp_transport),
                "document_process_mcp",
            )
            procs["voice_mcp"] = start_process(
                build_voice_mcp_command(use_uv=use_uv, transport=mcp_transport),
                "voice_process_mcp",
            )
            if mcp_transport == "http" and not args.no_wait:
                if not wait_for_mcp_http(
                    doc_mcp_url, name="document_process_mcp", timeout=args.mcp_timeout
                ):
                    _shutdown()
                    return 1
                if not wait_for_mcp_http(
                    voice_mcp_url, name="voice_process_mcp", timeout=args.mcp_timeout
                ):
                    _shutdown()
                    return 1
            else:
                time.sleep(0.5)

        if start_maf:
            procs["maf"] = start_process(build_maf_command(use_uv=use_uv), "MAF")
            time.sleep(0.4)
            if procs["maf"].poll() is not None:
                print("MAF failed to start. Install: uv sync --extra all-components --group dev", file=sys.stderr)
                _shutdown()
                return 1
            if not args.no_wait and not wait_for_maf(timeout=args.maf_timeout):
                _shutdown()
                return 1

        if start_api:
            procs["api"] = start_process(build_api_command(use_uv=use_uv), "FastAPI")
            time.sleep(0.4)
            if procs["api"].poll() is not None:
                print(
                    "FastAPI failed to start. Install deps first:\n"
                    "  uv sync --extra all-components --group dev\n"
                    "  or: pip install -r requirements-dev.txt\n",
                    file=sys.stderr,
                )
                _shutdown()
                return 1

        if args.maf_only:
            print(f"MAF running on http://{maf_host}:{maf_port}")
            print(f"Ask:  POST {maf_base}/ask")
            print(f"Health: GET {maf_base}/health")
            return procs["maf"].wait() if procs["maf"] else 0

        if args.api_only:
            print(f"API running on http://{api_host}:{api_port}")
            print(f"Docs: http://127.0.0.1:{api_port}/docs")
            if procs["maf"]:
                print(f"MAF:  {maf_base}")
            if procs["doc_mcp"] and mcp_transport == "http":
                print(f"document_process_mcp: {doc_mcp_url}")
            if procs["voice_mcp"] and mcp_transport == "http":
                print(f"voice_process_mcp:    {voice_mcp_url}")
            return procs["api"].wait() if procs["api"] else 0

        if args.mcp_only:
            if mcp_transport == "http":
                print(f"document_process_mcp: {doc_mcp_url}")
                print(f"voice_process_mcp:    {voice_mcp_url}")
            else:
                print("MCP servers running in stdio mode.")
            print("Press Ctrl+C to stop.")
            while True:
                for key in ("doc_mcp", "voice_mcp"):
                    proc = procs[key]
                    if proc is not None and proc.poll() is not None:
                        print(f"{key} exited unexpectedly.", file=sys.stderr)
                        _shutdown()
                        return proc.returncode or 1
                time.sleep(0.5)

        if start_api and not args.no_wait:
            if not wait_for_api(timeout=args.api_timeout):
                _shutdown()
                return 1

        if start_ui:
            procs["ui"] = start_process(build_ui_command(use_uv=use_uv), "Gradio UI")
            time.sleep(0.4)
            if procs["ui"].poll() is not None:
                print("Gradio UI failed to start.", file=sys.stderr)
                _shutdown()
                return 1

        print("")
        print("=" * 64)
        print("  Document Processing — ALL COMPONENTS")
        print("=" * 64)
        if procs["api"]:
            print(f"  API:                 http://127.0.0.1:{api_port}")
            print(f"  Swagger:             http://127.0.0.1:{api_port}/docs")
            print(f"  Ask (via API):       POST http://127.0.0.1:{api_port}/api/ask")
        if procs["maf"]:
            print(f"  MAF:                 {maf_base}")
            print(f"  Ask (direct MAF):    POST {maf_base}/ask")
        if procs["ui"]:
            print(f"  UI:                  http://{gradio_host}:{gradio_port}")
        if procs["doc_mcp"] and mcp_transport == "http":
            print(f"  document_process_mcp:{doc_mcp_url}")
        if procs["voice_mcp"] and mcp_transport == "http":
            print(f"  voice_process_mcp:   {voice_mcp_url}")
        print("=" * 64)
        print("Press Ctrl+C to stop.")
        print("")

        while True:
            for key, label in (
                ("ui", "Gradio UI"),
                ("api", "FastAPI"),
                ("maf", "MAF"),
                ("doc_mcp", "document_process_mcp"),
                ("voice_mcp", "voice_process_mcp"),
            ):
                proc = procs[key]
                if proc is not None and proc.poll() is not None:
                    print(f"{label} exited unexpectedly.", file=sys.stderr)
                    code = proc.returncode or 1
                    _shutdown()
                    return code
            time.sleep(0.5)

    except KeyboardInterrupt:
        _shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
