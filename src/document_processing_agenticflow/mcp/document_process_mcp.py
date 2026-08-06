"""Separate FastMCP server: ``document_process_mcp`` (document LangGraph pipeline only)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from document_processing_agenticflow.mcp.base import BaseAgentMCPServer
from document_processing_agenticflow.services.naming import build_contract_output_filename

MCP_NAME = "document_process_mcp"


class DocumentProcessMCP(BaseAgentMCPServer):
    """Standalone MCP: Word template + JSON → filled .docx (LangGraph)."""

    def __init__(self, *, host: str | None = None, port: int | None = None) -> None:
        port = port if port is not None else int(os.getenv("DOCUMENT_MCP_PORT", "8001"))
        super().__init__(
            name=MCP_NAME,
            instructions=(
                "MCP server document_process_mcp. "
                "Fill a Word .docx template from JSON via LangGraph. "
                "Tools: health, generate_document."
            ),
            host=host,
            port=port,
            version="0.1.0",
        )

    def register_tools(self) -> None:
        @self.tool
        def health() -> dict[str, Any]:
            """Liveness check for document_process_mcp."""
            return {
                "ok": True,
                "mcp": MCP_NAME,
                "agent": "document_process_mcp",
                "transport": "http|stdio",
                "host": self.host,
                "port": self.port,
            }

        @self.tool
        def generate_document(
            template_path: str,
            data_path: str | None = None,
            data_json: str | None = None,
            output_path: str | None = None,
            skip_validation: bool = False,
            skip_extraction_validation: bool = False,
            max_retries: int = 1,
            validation_threshold: float = 0.7,
        ) -> dict[str, Any]:
            """
            Run the LangGraph document pipeline (extract → map → generate → validate).

            Provide either ``data_path`` (JSON file) or ``data_json`` (JSON object string).
            """
            import time

            from document_processing_agenticflow.core.request_context import bind_xid, require_xid
            from document_processing_agenticflow.graph import invoke_document_graph
            from document_processing_agenticflow.services.trace_log import log_event

            xid = require_xid()
            started = time.perf_counter()
            with bind_xid(xid):
                tpl = Path(template_path).expanduser().resolve()
                if not tpl.is_file():
                    return {"ok": False, "error": f"template not found: {tpl}", "xid": xid}

                if data_path:
                    data_file = Path(data_path).expanduser().resolve()
                    if not data_file.is_file():
                        return {
                            "ok": False,
                            "error": f"data file not found: {data_file}",
                            "xid": xid,
                        }
                elif data_json:
                    try:
                        payload = json.loads(data_json)
                    except json.JSONDecodeError as exc:
                        return {"ok": False, "error": f"invalid data_json: {exc}", "xid": xid}
                    if not isinstance(payload, dict):
                        return {
                            "ok": False,
                            "error": "data_json root must be an object",
                            "xid": xid,
                        }
                    tmp_dir = Path(os.getenv("STORAGE_BASE_PATH", "./data/storage")) / "mcp_tmp"
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    data_file = tmp_dir / f"data_{uuid.uuid4().hex}.json"
                    data_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                else:
                    return {"ok": False, "error": "Provide data_path or data_json", "xid": xid}

                if output_path:
                    out = Path(output_path).expanduser().resolve()
                else:
                    job_suffix = uuid.uuid4().hex
                    out_dir = Path(os.getenv("STORAGE_BASE_PATH", "./data/storage")) / "mcp_out"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out = out_dir / build_contract_output_filename(job_suffix, tpl.name)

                out.parent.mkdir(parents=True, exist_ok=True)
                result = invoke_document_graph(
                    {
                        "template_path": str(tpl),
                        "data_path": str(data_file),
                        "output_path": str(out),
                        "errors": [],
                        "status": "started",
                        "retry_count": 0,
                        "max_retries": max_retries,
                        "validation_threshold": validation_threshold,
                        "skip_validation": skip_validation,
                        "skip_extraction_validation": skip_extraction_validation,
                    }
                )
                status = result.get("status")
                errors = result.get("errors") or []
                confidence = result.get("confidence")
                extraction = result.get("extraction_validation")
                validation = result.get("validation")
                generation = result.get("generation")
                payload_out = {
                    "ok": status == "completed" and not errors,
                    "mcp": MCP_NAME,
                    "xid": xid,
                    "status": status,
                    "errors": errors,
                    "output_path": generation.output_path if generation else str(out),
                    "confidence": confidence.model_dump() if confidence else None,
                    "extraction_validation": extraction.model_dump() if extraction else None,
                    "validation": validation.model_dump() if validation else None,
                }
                log_event(
                    kind="mcp_tool",
                    name="generate_document",
                    request_payload={
                        "template_path": str(tpl),
                        "data_path": str(data_file),
                        "output_path": str(out),
                    },
                    response_payload={
                        "ok": payload_out["ok"],
                        "status": status,
                        "errors": errors,
                        "output_path": payload_out["output_path"],
                    },
                    status="ok" if payload_out["ok"] else "error",
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    xid=xid,
                )
                return payload_out


def main(argv: list[str] | None = None) -> int:
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="document_process_mcp FastMCP server")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default=os.getenv("DOCUMENT_MCP_TRANSPORT", "http"),
    )
    parser.add_argument("--host", default=os.getenv("DOCUMENT_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("DOCUMENT_MCP_PORT", "8001")),
    )
    parser.add_argument("--banner", action="store_true")
    args = parser.parse_args(argv)

    server = DocumentProcessMCP(host=args.host, port=args.port)
    if args.transport == "stdio":
        server.run_stdio(show_banner=args.banner)
    else:
        print(f"{MCP_NAME} listening on http://{args.host}:{args.port}/mcp")
        server.run_http(show_banner=args.banner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
