"""Start FastAPI + Gradio UI + document_process_mcp + voice_process_mcp (`python run_both.py` / `uv run doc-app`)."""

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _api_url() -> str:
    base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/health"


def wait_for_api(timeout: float = 60.0, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    url = _api_url()
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                print(f"API ready: {url}")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(interval)
    print(f"Timed out waiting for API at {url}", file=sys.stderr)
    return False


def _python_cmd() -> list[str]:
    return [sys.executable]


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(SRC_ROOT)
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if src not in parts:
        env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


def build_api_command(*, use_uv: bool) -> list[str]:
    if use_uv and shutil.which("uv"):
        return ["uv", "run", "doc-api"]
    return [
        *_python_cmd(),
        "-m",
        "uvicorn",
        "document_processing_agenticflow.api.main:app",
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
        "document_processing_agenticflow.ui.gradio_app",
    ]


def build_document_mcp_command(*, use_uv: bool, transport: str = "http") -> list[str]:
    """Build command for document_process_mcp. Default transport is HTTP for FastAPI clients."""
    host = os.getenv("DOCUMENT_MCP_HOST", "127.0.0.1")
    port = str(_env_int("DOCUMENT_MCP_PORT", 8001))
    base: list[str]
    if use_uv and shutil.which("uv"):
        base = ["uv", "run", "document-process-mcp"]
    else:
        base = [
            *_python_cmd(),
            "-m",
            "document_processing_agenticflow.mcp.document_process_mcp",
        ]
    cmd = [*base, "--transport", transport]
    if transport == "http":
        cmd.extend(["--host", host, "--port", port])
    return cmd


def build_voice_mcp_command(*, use_uv: bool, transport: str = "http") -> list[str]:
    """Build command for voice_process_mcp. Default transport is HTTP for FastAPI clients."""
    host = os.getenv("VOICE_MCP_HOST", "127.0.0.1")
    port = str(_env_int("VOICE_MCP_PORT", 8002))
    base: list[str]
    if use_uv and shutil.which("uv"):
        base = ["uv", "run", "voice-process-mcp"]
    else:
        base = [
            *_python_cmd(),
            "-m",
            "document_processing_agenticflow.mcp.voice_process_mcp",
        ]
    cmd = [*base, "--transport", transport]
    if transport == "http":
        cmd.extend(["--host", host, "--port", port])
    return cmd


def wait_for_mcp_http(url: str, *, name: str, timeout: float = 30.0, interval: float = 0.4) -> bool:
    """Wait until an MCP Streamable HTTP endpoint accepts connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # MCP /mcp may return 4xx on plain GET; any TCP response means the server is up.
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code < 500:
                print(f"{name} ready: {url}")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(interval)
    print(f"Timed out waiting for {name} at {url}", file=sys.stderr)
    return False


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ALL services: FastAPI + Gradio + document_process_mcp + voice_process_mcp"
    )
    parser.add_argument("--api-only", action="store_true", help="Start FastAPI backend only")
    parser.add_argument(
        "--ui-only",
        action="store_true",
        help="Start Gradio UI only (API must already run)",
    )
    parser.add_argument(
        "--mcp-only",
        action="store_true",
        help="Start document_process_mcp + voice_process_mcp only (HTTP by default)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Do not start FastMCP agents (API + UI only)",
    )
    parser.add_argument(
        "--mcp-transport",
        choices=["http", "stdio"],
        default=os.getenv("MCP_TRANSPORT", "http"),
        help="MCP transport for both servers (default: http). Use http so FastAPI can call /mcp.",
    )
    parser.add_argument(
        "--mcp-http",
        action="store_true",
        help="Force MCP HTTP mode (same as --mcp-transport http)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for API/MCP health checks before launching UI",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for API health (default: 60)",
    )
    parser.add_argument(
        "--mcp-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for MCP HTTP endpoints (default: 30)",
    )
    parser.add_argument(
        "--use-uv",
        action="store_true",
        help="Launch children via `uv run` entry points",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    args = parse_args(argv)
    use_uv = bool(args.use_uv)
    mcp_transport = "http" if args.mcp_http else str(args.mcp_transport)
    if mcp_transport == "stdio" and not args.mcp_only:
        print(
            "MCP stdio cannot be used with FastAPI agent proxies; forcing --mcp-transport http.",
            file=sys.stderr,
        )
        mcp_transport = "http"
    # Keep child MCP CLIs and clients aligned with the launcher choice.
    os.environ["DOCUMENT_MCP_TRANSPORT"] = mcp_transport
    os.environ["VOICE_MCP_TRANSPORT"] = mcp_transport
    os.environ["MCP_TRANSPORT"] = mcp_transport

    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = _env_int("API_PORT", 8000)
    gradio_host = os.getenv("GRADIO_HOST", "127.0.0.1")
    gradio_port = _env_int("GRADIO_PORT", 7860)
    doc_mcp_host = os.getenv("DOCUMENT_MCP_HOST", "127.0.0.1")
    doc_mcp_port = _env_int("DOCUMENT_MCP_PORT", 8001)
    voice_mcp_host = os.getenv("VOICE_MCP_HOST", "127.0.0.1")
    voice_mcp_port = _env_int("VOICE_MCP_PORT", 8002)
    doc_mcp_url = os.getenv("DOCUMENT_MCP_URL", f"http://{doc_mcp_host}:{doc_mcp_port}/mcp").rstrip("/")
    voice_mcp_url = os.getenv("VOICE_MCP_URL", f"http://{voice_mcp_host}:{voice_mcp_port}/mcp").rstrip("/")

    procs: dict[str, subprocess.Popen | None] = {
        "api": None,
        "ui": None,
        "doc_mcp": None,
        "voice_mcp": None,
    }

    def _shutdown(signum: int | None = None, _frame: object | None = None) -> None:
        del signum, _frame
        terminate_process(procs["ui"], "Gradio UI")
        terminate_process(procs["api"], "FastAPI")
        terminate_process(procs["doc_mcp"], "document_process_mcp")
        terminate_process(procs["voice_mcp"], "voice_process_mcp")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        start_mcp = not args.no_mcp and not args.ui_only
        start_api = not args.ui_only and not args.mcp_only
        start_ui = not args.api_only and not args.mcp_only

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

        if start_api:
            procs["api"] = start_process(build_api_command(use_uv=use_uv), "FastAPI")
            time.sleep(0.4)
            if procs["api"].poll() is not None:
                print(
                    "FastAPI failed to start. Install deps first:\n"
                    "  uv sync\n"
                    "  or: pip install -r requirements.txt\n",
                    file=sys.stderr,
                )
                _shutdown()
                return 1

        if args.api_only:
            print(f"API running on http://{api_host}:{api_port}")
            print(f"Docs: http://127.0.0.1:{api_port}/docs")
            if procs["doc_mcp"] and mcp_transport == "http":
                print(f"document_process_mcp (http): {doc_mcp_url}")
            if procs["voice_mcp"] and mcp_transport == "http":
                print(f"voice_process_mcp (http):    {voice_mcp_url}")
            return procs["api"].wait() if procs["api"] else 0

        if args.mcp_only:
            if mcp_transport == "http":
                print(f"document_process_mcp (http): {doc_mcp_url}")
                print(f"voice_process_mcp (http):    {voice_mcp_url}")
            else:
                print("MCP servers running in stdio mode (no HTTP endpoints).")
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
        print("=" * 60)
        print("  Document Processing Agentic Flow — ALL SERVICES")
        print("=" * 60)
        if procs["api"]:
            print(f"  API:              http://127.0.0.1:{api_port}")
            print(f"  Swagger:          http://127.0.0.1:{api_port}/docs")
            print(f"  Agents health:    http://127.0.0.1:{api_port}/api/v1/agents/health")
        if procs["ui"]:
            print(f"  UI:               http://{gradio_host}:{gradio_port}")
        if procs["doc_mcp"] and mcp_transport == "http":
            print(f"  document_process_mcp (http): {doc_mcp_url}")
        if procs["voice_mcp"] and mcp_transport == "http":
            print(f"  voice_process_mcp (http):    {voice_mcp_url}")
        print("=" * 60)
        print("Press Ctrl+C to stop.")
        print("")

        while True:
            for key, label in (
                ("ui", "Gradio UI"),
                ("api", "FastAPI"),
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
