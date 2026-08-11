"""Microsoft Agent Framework (MAF) orchestrator for local runs.

Thin layer: user message → MAF Agent (LLM + tool calling) → existing FastMCP servers
(`document_process_mcp`, `voice_process_mcp`) over HTTP streamable MCP.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INSTRUCTIONS = """\
You are the document-processing orchestrator for this local stack.

You have two MCP tool servers:
1) document_process_mcp — fill a Word .docx template from JSON
   (tools usually prefixed document_*): health, generate_document
2) voice_process_mcp — voice/text create-contract with HITL confirm
   (tools usually prefixed voice_*): health, start_voice_contract,
   confirm_voice_contract, list_voice_contracts

Rules:
- Prefer calling tools instead of inventing file paths or contract results.
- Tool names are prefixed: document_health, document_generate_document,
  voice_health, voice_start_voice_contract, voice_confirm_voice_contract,
  voice_list_voice_contracts.
- For document generation, call document_generate_document with template_path and
  either data_path or data_json. Paths may be project-relative.
- For spoken/typed contract creation, call voice_start_voice_contract; if the tool
  says confirmation is needed, ask the user and then call voice_confirm_voice_contract.
- Keep answers concise; include tool outcomes (paths, ids, status, errors).
"""


def _component_root() -> Path:
    """central-agentic-flow/ (contains prompts/ + src/)."""
    return Path(__file__).resolve().parents[2]


def prompts_dir() -> Path:
    override = (
        os.getenv("MAF_PROMPTS_DIR", "").strip()
        or os.getenv("PROMPTS_DIR", "").strip()
    )
    if override:
        return Path(override).expanduser().resolve()
    return (_component_root() / "prompts").resolve()


def load_maf_instructions() -> str:
    """Resolve MAF system instructions: env → prompts file → default."""
    inline = _clean(os.getenv("MAF_INSTRUCTIONS"))
    if inline:
        return inline
    file_override = _clean(os.getenv("MAF_INSTRUCTIONS_FILE"))
    candidates: list[Path] = []
    if file_override:
        candidates.append(Path(file_override).expanduser())
    candidates.append(prompts_dir() / "orchestrator_instructions.md")
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                # Drop markdown title line if present
                lines = text.splitlines()
                if lines and lines[0].lstrip().startswith("#"):
                    text = "\n".join(lines[1:]).strip()
                if text:
                    return text
    return DEFAULT_INSTRUCTIONS


@dataclass(frozen=True)
class MafAskResult:
    text: str
    response_id: str | None = None
    raw: Any | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = _clean(os.getenv(name))
        if value:
            return value
    return default


def resolve_maf_chat_client():
    """Build an OpenAI-compatible chat client from env (OpenAI / Azure / Groq / compatible)."""
    from agent_framework.openai import OpenAIChatClient

    provider = (_env("MAF_PROVIDER", "AGENT_PROVIDER") or "openai").lower()
    model = _env(
        "MAF_MODEL",
        "AGENT_MODEL",
        "OPENAI_MODEL",
        "AZURE_OPENAI_DEPLOYMENT",
        default="gpt-4o-mini",
    )

    # MAF_BASE_URL is the HTTP service (:8003). LLM endpoint override is MAF_LLM_BASE_URL.
    if provider in {"azure", "azure_openai", "azure-openai"}:
        endpoint = _env("MAF_LLM_BASE_URL", "AZURE_OPENAI_ENDPOINT")
        api_key = _env("MAF_API_KEY", "AZURE_OPENAI_API_KEY")
        api_version = _env("MAF_API_VERSION", "AZURE_OPENAI_API_VERSION", default="2024-12-01-preview")
        if not endpoint or not api_key:
            raise RuntimeError(
                "MAF azure_openai needs AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY "
                "(or MAF_LLM_BASE_URL + MAF_API_KEY)."
            )
        return OpenAIChatClient(
            model=model,
            api_key=api_key,
            azure_endpoint=endpoint.rstrip("/"),
            api_version=api_version,
        )

    if provider == "groq":
        api_key = _env("MAF_API_KEY", "GROQ_API_KEY")
        base_url = _env(
            "MAF_LLM_BASE_URL",
            "GROQ_BASE_URL",
            default="https://api.groq.com/openai/v1",
        )
        model = _env("MAF_MODEL", "AGENT_MODEL", "GROQ_MODEL", "GROQ_VALIDATOR_MODEL", default=model)
        if not api_key:
            raise RuntimeError("MAF groq needs GROQ_API_KEY (or MAF_API_KEY).")
        return OpenAIChatClient(model=model, api_key=api_key, base_url=base_url)

    if provider in {"openai_compatible", "compatible", "ollama"}:
        api_key = _env("MAF_API_KEY", "COMPATIBLE_API_KEY", "OPENAI_API_KEY", default="EMPTY")
        base_url = _env("MAF_LLM_BASE_URL", "COMPATIBLE_BASE_URL", "OLLAMA_BASE_URL")
        if not base_url:
            raise RuntimeError(
                "MAF openai_compatible needs MAF_LLM_BASE_URL or COMPATIBLE_BASE_URL "
                "(e.g. http://127.0.0.1:11434/v1)."
            )
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        return OpenAIChatClient(model=model, api_key=api_key, base_url=base_url)

    # default: OpenAI
    api_key = _env("MAF_API_KEY", "OPENAI_API_KEY", "AGENT_API_KEY")
    base_url = _env("MAF_LLM_BASE_URL", "OPENAI_BASE_URL")
    if not api_key:
        raise RuntimeError("MAF openai needs OPENAI_API_KEY (or MAF_API_KEY).")
    kwargs: dict[str, Any] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIChatClient(**kwargs)


def document_mcp_url() -> str:
    return (_env("DOCUMENT_MCP_URL", default="http://127.0.0.1:8001/mcp") or "").rstrip("/")


def voice_mcp_url() -> str:
    return (_env("VOICE_MCP_URL", default="http://127.0.0.1:8002/mcp") or "").rstrip("/")


def maf_request_timeout() -> int:
    raw = _env("MAF_MCP_TIMEOUT_SECONDS", default="300") or "300"
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


async def ask_maf(message: str, *, instructions: str | None = None) -> MafAskResult:
    """Run one MAF turn against both local MCP HTTP servers."""
    from agent_framework import Agent, MCPStreamableHTTPTool

    text = (message or "").strip()
    if not text:
        raise ValueError("message must be non-empty")

    timeout = maf_request_timeout()
    client = resolve_maf_chat_client()
    system = instructions or load_maf_instructions()

    async with (
        MCPStreamableHTTPTool(
            name="document_process_mcp",
            url=document_mcp_url(),
            description="Word template + JSON document generation (LangGraph pipeline).",
            tool_name_prefix="document",
            approval_mode="never_require",
            request_timeout=timeout,
        ) as document_mcp,
        MCPStreamableHTTPTool(
            name="voice_process_mcp",
            url=voice_mcp_url(),
            description="Voice/text create-contract with human-in-the-loop confirm.",
            tool_name_prefix="voice",
            approval_mode="never_require",
            request_timeout=timeout,
        ) as voice_mcp,
        Agent(
            client=client,
            name="DocumentOrchestrator",
            instructions=system,
            tools=[document_mcp, voice_mcp],
        ) as agent,
    ):
        response = await agent.run(text)

    return MafAskResult(
        text=getattr(response, "text", None) or str(response),
        response_id=getattr(response, "response_id", None),
        raw=response,
    )
