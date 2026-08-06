"""Separate FastMCP server: ``voice_process_mcp`` (voice → contract LangGraph only)."""

from __future__ import annotations

import os
from typing import Any

from document_processing_agenticflow.mcp.base import BaseAgentMCPServer

MCP_NAME = "voice_process_mcp"


class VoiceProcessMCP(BaseAgentMCPServer):
    """Standalone MCP: voice/text create-contract with HITL confirm (LangGraph)."""

    def __init__(self, *, host: str | None = None, port: int | None = None) -> None:
        port = port if port is not None else int(os.getenv("VOICE_MCP_PORT", "8002"))
        super().__init__(
            name=MCP_NAME,
            instructions=(
                "MCP server voice_process_mcp. "
                "Voice/text → create-contract with human-in-the-loop. "
                "Tools: health, start_voice_contract, confirm_voice_contract, list_voice_contracts."
            ),
            host=host,
            port=port,
            version="0.1.0",
        )

    def register_tools(self) -> None:
        @self.tool
        def health() -> dict[str, Any]:
            """Liveness check for voice_process_mcp."""
            return {
                "ok": True,
                "mcp": MCP_NAME,
                "agent": "voice_process_mcp",
                "transport": "http|stdio",
                "host": self.host,
                "port": self.port,
            }

        @self.tool
        def start_voice_contract(
            transcript: str,
            auto_create: bool = False,
        ) -> dict[str, Any]:
            """Start the voice-contract LangGraph agent (may return needs_confirmation)."""
            from document_processing_agenticflow.services.voice_contract_workflow import (
                run_voice_contract_workflow,
            )
            from document_processing_agenticflow.storage.job_store import JobStore

            store = JobStore()
            result = run_voice_contract_workflow(
                transcript,
                store=store,
                auto_create=auto_create,
            )
            payload = result.to_dict()
            payload["mcp"] = MCP_NAME
            if result.ok and result.status == "completed":
                saved = store.save_voice_contract(
                    spoken_name=result.spoken_name or "",
                    spoken_number=result.spoken_number or "",
                    contact=result.contact or result.legal_entity,
                    legal_entity=result.legal_entity,
                    pricelist=result.pricelist,
                    contract_payload=result.contract_payload,
                    contract_file=result.contract_file,
                    transcript=result.transcript,
                )
                payload["contract_id"] = saved.get("contract_id")
            return payload

        @self.tool
        def confirm_voice_contract(
            legal_entity: str,
            contract_reference_number: str,
            thread_id: str | None = None,
            user_text: str = "yes",
            transcript: str | None = None,
        ) -> dict[str, Any]:
            """Resume HITL interrupt (preferred with thread_id) or finalize by entity/ref."""
            from document_processing_agenticflow.services.voice_contract_workflow import (
                confirm_voice_contract as confirm_fn,
            )
            from document_processing_agenticflow.storage.job_store import JobStore

            store = JobStore()
            result = confirm_fn(
                entity_code_or_name=legal_entity,
                contract_reference_number=contract_reference_number,
                store=store,
                transcript=transcript,
                thread_id=thread_id,
                user_text=user_text,
            )
            payload = result.to_dict()
            payload["mcp"] = MCP_NAME
            if result.ok and result.status == "completed":
                saved = store.save_voice_contract(
                    spoken_name=result.spoken_name or "",
                    spoken_number=result.spoken_number or "",
                    contact=result.contact or result.legal_entity,
                    legal_entity=result.legal_entity,
                    pricelist=result.pricelist,
                    contract_payload=result.contract_payload,
                    contract_file=result.contract_file,
                    transcript=result.transcript,
                )
                payload["contract_id"] = saved.get("contract_id")
                payload["message"] = (
                    f"{result.message} Saved to SQLite as contract `{saved['contract_id']}`."
                )
            return payload

        @self.tool
        def list_voice_contracts(limit: int = 20) -> dict[str, Any]:
            """List saved voice contracts from SQLite."""
            from document_processing_agenticflow.storage.job_store import JobStore

            store = JobStore()
            rows = store.list_voice_contracts(limit=limit)
            return {"mcp": MCP_NAME, "count": len(rows), "contracts": rows}


def main(argv: list[str] | None = None) -> int:
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="voice_process_mcp FastMCP server")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default=os.getenv("VOICE_MCP_TRANSPORT", "http"),
    )
    parser.add_argument("--host", default=os.getenv("VOICE_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("VOICE_MCP_PORT", "8002")),
    )
    parser.add_argument("--banner", action="store_true")
    args = parser.parse_args(argv)

    server = VoiceProcessMCP(host=args.host, port=args.port)
    if args.transport == "stdio":
        server.run_stdio(show_banner=args.banner)
    else:
        print(f"{MCP_NAME} listening on http://{args.host}:{args.port}/mcp")
        server.run_http(show_banner=args.banner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
