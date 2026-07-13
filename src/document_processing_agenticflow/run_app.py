"""Start FastAPI + Gradio UI together (`uv run doc-app`)."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def start_process(cmd: list[str], name: str) -> subprocess.Popen:
    print(f"Starting {name}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=PROJECT_ROOT, env=os.environ.copy())


def terminate_process(proc: subprocess.Popen | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    print(f"Stopping {name} (pid {proc.pid})...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Document Processing Agentic Flow app")
    parser.add_argument("--api-only", action="store_true", help="Start FastAPI backend only")
    parser.add_argument("--ui-only", action="store_true", help="Start Gradio UI only (API must already run)")
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    args = parse_args(argv)
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = _env_int("API_PORT", 8000)
    gradio_host = os.getenv("GRADIO_HOST", "127.0.0.1")
    gradio_port = _env_int("GRADIO_PORT", 7860)

    api_cmd = ["uv", "run", "doc-api"]
    ui_cmd = ["uv", "run", "doc-ui"]

    api_proc: subprocess.Popen | None = None
    ui_proc: subprocess.Popen | None = None

    def _shutdown(signum: int | None = None, _frame: object | None = None) -> None:
        del signum, _frame
        terminate_process(ui_proc, "Gradio UI")
        terminate_process(api_proc, "FastAPI")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        if not args.ui_only:
            api_proc = start_process(api_cmd, "FastAPI")
            if api_proc.poll() is not None:
                print("FastAPI failed to start.", file=sys.stderr)
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

        ui_exit = ui_proc.wait()
        terminate_process(api_proc, "FastAPI")
        return ui_exit

    except KeyboardInterrupt:
        _shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
