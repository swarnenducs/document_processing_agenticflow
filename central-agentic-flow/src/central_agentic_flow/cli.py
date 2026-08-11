"""CLI: `uv run doc-maf-ask "..." ` — local MAF → MCP smoke run."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Run one Microsoft Agent Framework ask against local MCP servers.",
    )
    parser.add_argument("message", nargs="?", help="User message for the orchestrator")
    parser.add_argument(
        "-m",
        "--message",
        dest="message_flag",
        help="User message (alternative to positional)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON {text, response_id}")
    args = parser.parse_args(argv)
    message = (args.message_flag or args.message or "").strip()
    if not message:
        parser.error("Provide a message, e.g. uv run doc-maf-ask 'list voice MCP tools via health'")

    from central_agentic_flow.orchestrator import ask_maf

    result = asyncio.run(ask_maf(message))
    if args.json:
        print(json.dumps({"text": result.text, "response_id": result.response_id}, indent=2))
    else:
        print(result.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
