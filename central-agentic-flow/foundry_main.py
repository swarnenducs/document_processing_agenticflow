"""Microsoft Foundry hosted-agent entry point (Responses protocol)."""

from __future__ import annotations

import asyncio

from central_agentic_flow.foundry_server import run_foundry_server


if __name__ == "__main__":
    asyncio.run(run_foundry_server())
