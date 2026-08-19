"""In-process stand-in for MAF → voice tools (no voice_enable_mcp import)."""

from __future__ import annotations

from typing import Any


async def invoke_tool_double(server: str, tool: str, arguments: dict[str, Any] | None = None) -> Any:
    arguments = arguments or {}
    if server != "voice":
        raise RuntimeError("central agent unavailable in tests")

    from ip_api.storage.job_store import JobStore

    store = JobStore()
    if tool == "start_voice_contract":
        transcript = str(arguments.get("transcript") or "")
        if "create contract" not in transcript.lower():
            return {
                "ok": False,
                "status": "rejected",
                "message": "Please ask a relevant service.",
                "contract_id": None,
            }
        return {
            "ok": False,
            "status": "needs_confirmation",
            "thread_id": "thread-test",
            "contract_reference_number": "CR-1001",
            "legal_entity": {"code": "AVC", "legalName": "AVC"},
            "transcript": transcript,
            "message": "Confirm this contract?",
        }
    if tool == "confirm_voice_contract":
        payload = {
            "contractReferenceNumber": "CR-1001",
            "legalName": "AVC",
            "legalEntityCode": "AVC",
        }
        saved = store.save_voice_contract(
            spoken_name="AVC",
            spoken_number="CR-1001",
            legal_entity={"code": "AVC", "legalName": "AVC"},
            contract_payload=payload,
            transcript=arguments.get("transcript"),
        )
        cid = saved["contract_id"]
        return {
            "ok": True,
            "status": "completed",
            "contract_id": cid,
            "contract_text": "SUPPLY CONTRACT (DUMMY)",
            "contract_payload": payload,
            "message": f"Created. Saved to SQLite as contract `{cid}`.",
        }
    if tool == "list_voice_contracts":
        rows = store.list_voice_contracts(limit=int(arguments.get("limit") or 50))
        return {"count": len(rows), "contracts": rows, "mcp": "voice_process_mcp"}
    raise RuntimeError(f"unknown voice tool {tool}")
