"""Start FastAPI + Gradio UI together (`python run_both.py` or `uv run doc-app`)."""

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
    """Prefer current interpreter; fall back to ``uv run`` only if requested."""
    return [sys.executable]


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    # Ensure `import document_processing_agenticflow` works for child processes.
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


def start_process(cmd: list[str], name: str) -> subprocess.Popen:
    print(f"Starting {name}: {' '.join(cmd)}")
    kwargs: dict = {
        "cwd": str(PROJECT_ROOT),
        "env": _child_env(),
    }
    # On Windows, start in a new process group so Ctrl+C / terminate is cleaner.
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
        description="Run Document Processing Agentic Flow (API + Gradio UI)"
    )
    parser.add_argument("--api-only", action="store_true", help="Start FastAPI backend only")
    parser.add_argument(
        "--ui-only",
        action="store_true",
        help="Start Gradio UI only (API must already run)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for API health check before launching UI",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for API health (default: 60)",
    )
    parser.add_argument(
        "--use-uv",
        action="store_true",
        help="Launch children via `uv run doc-api/doc-ui` instead of python -m",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    args = parse_args(argv)
    use_uv = bool(args.use_uv)
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = _env_int("API_PORT", 8000)
    gradio_host = os.getenv("GRADIO_HOST", "127.0.0.1")
    gradio_port = _env_int("GRADIO_PORT", 7860)

    api_cmd = build_api_command(use_uv=use_uv)
    ui_cmd = build_ui_command(use_uv=use_uv)

    api_proc: subprocess.Popen | None = None
    ui_proc: subprocess.Popen | None = None

    def _shutdown(signum: int | None = None, _frame: object | None = None) -> None:
        del signum, _frame
        terminate_process(ui_proc, "Gradio UI")
        terminate_process(api_proc, "FastAPI")
        sys.exit(0)

    # SIGTERM is not always useful on Windows; still register what we can.
    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        if not args.ui_only:
            api_proc = start_process(api_cmd, "FastAPI")
            time.sleep(0.4)
            if api_proc.poll() is not None:
                print(
                    "FastAPI failed to start. Install deps first:\n"
                    "  uv sync\n"
                    "  or: pip install -r requirements.txt\n",
                    file=sys.stderr,
                )
                return 1

        if args.api_only:
            print(f"API running on http://{api_host}:{api_port}")
            print(f"Docs: http://127.0.0.1:{api_port}/docs")
            return api_proc.wait() if api_proc else 0

        if not args.ui_only and not args.no_wait:
            if not wait_for_api(timeout=args.api_timeout):
                _shutdown()
                return 1

        ui_proc = start_process(ui_cmd, "Gradio UI")
        time.sleep(0.4)
        if ui_proc.poll() is not None:
            print("Gradio UI failed to start.", file=sys.stderr)
            _shutdown()
            return 1

        print("")
        print("=" * 56)
        print("  Document Processing Agentic Flow")
        print("=" * 56)
        if api_proc:
            print(f"  API:     http://127.0.0.1:{api_port}")
            print(f"  Swagger: http://127.0.0.1:{api_port}/docs")
        print(f"  UI:      http://{gradio_host}:{gradio_port}")
        print("=" * 56)
        print("Press Ctrl+C to stop.")
        print("")

        # Wait until either child exits.
        while True:
            if ui_proc.poll() is not None:
                code = ui_proc.returncode or 0
                terminate_process(api_proc, "FastAPI")
                return code
            if api_proc is not None and api_proc.poll() is not None:
                print("API process exited unexpectedly.", file=sys.stderr)
                terminate_process(ui_proc, "Gradio UI")
                return api_proc.returncode or 1
            time.sleep(0.5)

    except KeyboardInterrupt:
        _shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
