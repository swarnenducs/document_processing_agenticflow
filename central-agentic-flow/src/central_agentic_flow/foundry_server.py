"""Microsoft Foundry Responses host for the business chat agent.

Chat and jobs stay segregated: document generation and voice contracts run on
the FastAPI service's deterministic ``POST /invoke`` path and are deliberately
not exposed here. This host only serves conversational business questions,
through an optional Foundry Toolbox.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from central_agentic_flow.orchestrator import load_maf_instructions

_COMPONENT_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_SETTINGS = (
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
)
_PLACEHOLDERS = {"...", "<replace-me>"}

_HOSTED_TOOL_INSTRUCTIONS = """

Foundry-hosted tool rules:
- Tools come from a Foundry Toolbox backed by the business MCP.
- MCP toolbox names use `{server_label}___{tool_name}` (three underscores),
  so business tools arrive as `business___<tool_name>`.
- Never invent tool output or business answers.
- Document generation and voice contracts are not available here. They run as API
  jobs on the orchestrator's `POST /invoke` path; say so instead of attempting them.
- Hosted tools must use HTTPS endpoints; never call localhost or private loopback addresses.
""".strip()


def missing_foundry_settings() -> list[str]:
    """Return required Foundry settings that are empty or placeholders."""
    missing: list[str] = []
    for name in _REQUIRED_SETTINGS:
        value = (os.getenv(name) or "").strip()
        if not value or value in _PLACEHOLDERS:
            missing.append(name)
    return missing


def toolbox_configured() -> bool:
    """Whether a business Toolbox is wired up. Chat works without one."""
    value = (os.getenv("TOOLBOX_ENDPOINT") or "").strip()
    return bool(value) and value not in _PLACEHOLDERS


def build_foundry_instructions() -> str:
    """Reuse the Web App MAF prompt and add hosted-tool naming rules."""
    override = (os.getenv("FOUNDRY_MAF_INSTRUCTIONS") or "").strip()
    base = override or load_maf_instructions()
    return f"{base.rstrip()}\n\n{_HOSTED_TOOL_INSTRUCTIONS}"


async def run_foundry_server() -> None:
    """Run the Foundry Responses protocol host on the platform-provided port."""
    load_dotenv(_COMPONENT_ROOT / ".env", override=False)
    missing = missing_foundry_settings()
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Foundry hosted chat agent is missing required settings: {joined}. "
            "Configure the Foundry project and model deployment."
        )

    # Keep optional Foundry dependencies isolated from the Web App runtime.
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    agent = Agent(
        client=client,
        instructions=build_foundry_instructions(),
        tools=FoundryToolbox(credential) if toolbox_configured() else None,
        default_options={"store": False},
    )
    server = ResponsesHostServer(agent)
    await server.run_async()
