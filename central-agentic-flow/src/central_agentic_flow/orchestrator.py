"""Microsoft Agent Framework (MAF) orchestrator for local runs.

Thin layer: user message → MAF Agent (LLM + tool calling) → existing FastMCP servers
(`document_process_mcp`, `voice_process_mcp`) over HTTP streamable MCP.
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from central_agentic_flow.chat_prompt import format_orchestrator_turn
from central_agentic_flow.mcp_registry import (
    ask_mcp_servers,
    build_agent_instructions,
    orchestrator_preamble_from_yaml,
)
from central_agentic_flow.prompt_catalog import (
    load_guardrail_instructions,
    load_markdown_prompt,
    load_orchestrator_prompt,
)


DEFAULT_INSTRUCTIONS = """\
You are the business chat orchestrator for this stack.

Rules:
- Only the MCP servers listed below are available; call them instead of inventing results.
- Tool names are prefixed with the MCP prefix (business_, ...).
- Document generation and voice contracts are not chat tools. They run as API jobs,
  so if asked for one, say it must be submitted through the API.
- Keep answers concise; include tool outcomes (ids, status, errors).
"""


def load_maf_instructions() -> str:
    """Resolve MAF system instructions: env → prompts file → default."""
    inline = _clean(os.getenv("MAF_INSTRUCTIONS"))
    if inline:
        return inline
    file_override = _clean(os.getenv("MAF_INSTRUCTIONS_FILE"))
    if file_override:
        override_path = Path(file_override).expanduser()
        if override_path.is_file():
            try:
                return load_markdown_prompt(override_path).body
            except ValueError:
                text = override_path.read_text(encoding="utf-8").strip()
                if text:
                    lines = text.splitlines()
                    if lines and lines[0].lstrip().startswith("#"):
                        text = "\n".join(lines[1:]).strip()
                    if text:
                        return text
    yaml_preamble = orchestrator_preamble_from_yaml()
    if yaml_preamble:
        return yaml_preamble
    spec = load_orchestrator_prompt()
    if spec is not None:
        return spec.body
    return DEFAULT_INSTRUCTIONS


@dataclass(frozen=True)
class MafAskResult:
    text: str
    response_id: str | None = None
    raw: Any | None = None
    role: str | None = None
    persona: str | None = None
    prompt: str | None = None
    version: str | None = None
    authorized: bool = True
    validation: dict[str, Any] | None = None


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


def _normalize_azure_endpoint(endpoint: str) -> tuple[str, str]:
    """Return (style, base_url) for classic Azure OpenAI vs Foundry v1."""
    url = endpoint.strip().rstrip("/")
    for suffix in ("/responses", "/chat/completions", "/completions"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
    if "services.ai.azure.com" in url.lower() or "/openai/v1" in url.lower():
        if not url.lower().endswith("/openai/v1"):
            url = f"{url}/openai/v1"
        return "foundry_v1", url
    return "classic", url


def _parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse ``provider:model`` the same way as LangChain ``init_chat_model``."""
    raw = model_id.strip()
    if ":" not in raw:
        raise ValueError(
            f"MAF_MODEL_ID must look like 'provider:model', got {model_id!r}. "
            "Example: openai:gpt-5-mini"
        )
    provider, _, model = raw.partition(":")
    provider = provider.strip().lower().replace("-", "_")
    model = model.strip()
    if not provider or not model:
        raise ValueError(f"Invalid MAF_MODEL_ID {model_id!r}: empty provider or model")
    return provider, model


def _foundry_v1_base() -> str | None:
    endpoint = _env("MAF_LLM_BASE_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_BASE_URL")
    if not endpoint:
        return None
    style, base = _normalize_azure_endpoint(endpoint)
    return base if style == "foundry_v1" else None


def resolve_maf_chat_client():
    """Build the MAF chat client from ``MAF_MODEL_ID=openai:gpt-5-mini`` (or split env).

    Selection matches LangChain ``init_chat_model("provider:model")``. The Agent
    Framework still needs ``OpenAIChatClient``, not a LangChain chat model.
    """
    from agent_framework.openai import OpenAIChatClient

    model_id = _env("MAF_MODEL_ID", "AGENT_MODEL_ID")
    if model_id:
        provider, model = _parse_model_id(model_id)
    else:
        provider = (_env("MAF_PROVIDER", "AGENT_PROVIDER") or "openai").lower()
        model = _env(
            "MAF_MODEL",
            "AGENT_MODEL",
            "OPENAI_MODEL",
            "AZURE_OPENAI_DEPLOYMENT",
            default="gpt-4o-mini",
        )

    if provider in {"azure", "azure-openai"}:
        provider = "azure_openai"

    # MAF_BASE_URL is the HTTP service (:8003). LLM endpoint override is MAF_LLM_BASE_URL.
    if provider == "azure_openai":
        endpoint = _env("MAF_LLM_BASE_URL", "AZURE_OPENAI_ENDPOINT")
        api_key = _env("MAF_API_KEY", "AZURE_OPENAI_API_KEY")
        api_version = _env("MAF_API_VERSION", "AZURE_OPENAI_API_VERSION", default="2024-12-01-preview")
        if not endpoint or not api_key:
            raise RuntimeError(
                "MAF azure_openai needs AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY "
                "(or MAF_LLM_BASE_URL + MAF_API_KEY)."
            )
        style, base = _normalize_azure_endpoint(endpoint)
        if style == "foundry_v1":
            return OpenAIChatClient(model=model, api_key=api_key, base_url=base)
        return OpenAIChatClient(
            model=model,
            api_key=api_key,
            azure_endpoint=base,
            api_version=api_version,
        )

    if provider == "groq":
        api_key = _env("MAF_API_KEY", "GROQ_API_KEY")
        base_url = _env(
            "MAF_LLM_BASE_URL",
            "GROQ_BASE_URL",
            default="https://api.groq.com/openai/v1",
        )
        if not model_id:
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

    # default: OpenAI  (``openai:gpt-5-mini``). Foundry v1 uses the same wire format.
    foundry = _foundry_v1_base()
    api_key = _env("MAF_API_KEY", "AZURE_OPENAI_API_KEY", "OPENAI_API_KEY", "AGENT_API_KEY") if foundry else _env(
        "MAF_API_KEY", "OPENAI_API_KEY", "AGENT_API_KEY"
    )
    base_url = _env("MAF_LLM_BASE_URL", "OPENAI_BASE_URL") or foundry
    if not api_key:
        raise RuntimeError(
            "MAF openai needs OPENAI_API_KEY, AZURE_OPENAI_API_KEY, or MAF_API_KEY."
        )
    kwargs: dict[str, Any] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIChatClient(**kwargs)


def maf_request_timeout() -> int:
    raw = _env("MAF_MCP_TIMEOUT_SECONDS", default="300") or "300"
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


async def ask_maf(
    message: str | None = None,
    *,
    instructions: str | None = None,
    role: str | None = None,
    persona: str | None = None,
    prompt: str | None = None,
) -> MafAskResult:
    """Validate request Persona vs Prompt with one LLM prompt, then maybe execute.

    Persona comes from the request. Chat tools are shared (not per-persona).
    Execute only if the validator JSON is allowed and confidence meets
    ``MAF_PERSONA_VALIDATOR_MIN_CONFIDENCE`` (default 0.95).
    """
    from agent_framework import Agent, MCPStreamableHTTPTool
    from central_agentic_flow.flow_debug import flow_breakpoint
    from central_agentic_flow.persona_validator import (
        describe_available_tools,
        should_execute,
        validate_user_prompt,
    )

    caller = (persona or role or "").strip()
    user_text = (prompt or message or "").strip()
    flow_breakpoint("ask_maf", message=user_text, role=caller, prompt=prompt)

    if not user_text:
        raise ValueError("Provide Prompt")
    if not caller:
        raise ValueError("Provide Persona")

    registry = ask_mcp_servers()
    timeout = maf_request_timeout()
    client = resolve_maf_chat_client()

    validation = await validate_user_prompt(
        client=client,
        persona_definition=caller,
        user_prompt=user_text,
        available_tools=describe_available_tools(registry),
    )
    authorized = should_execute(validation)
    persona_label = str(validation.get("persona") or caller.splitlines()[0][:80])
    if not authorized:
        reason = str(validation.get("reason") or "Prompt is not allowed for this persona.")
        return MafAskResult(
            text=reason,
            role=persona_label,
            persona=caller,
            prompt=user_text,
            version=str(validation.get("prompt_version") or None),
            authorized=False,
            validation=validation,
        )

    persona_block = (
        "Persona Definition (from the request; this is the authority for scope):\n"
        f"{caller}"
    )
    preamble = f"{load_maf_instructions().rstrip()}\n\n{persona_block}"
    system_raw = instructions or build_agent_instructions(preamble=preamble)
    guardrail = load_guardrail_instructions()
    if guardrail:
        system_raw = f"{system_raw.rstrip()}\n\n{guardrail}"
    system, formatted_user = format_orchestrator_turn(
        system_instructions=system_raw,
        message=user_text,
        persona=persona_label,
    )

    async with AsyncExitStack() as stack:
        tools = []
        for mcp_spec in registry:
            mcp_tool = await stack.enter_async_context(
                MCPStreamableHTTPTool(
                    name=mcp_spec.mcp_key,
                    url=mcp_spec.url,
                    description=mcp_spec.description,
                    tool_name_prefix=mcp_spec.prefix,
                    approval_mode="never_require",
                    request_timeout=timeout,
                )
            )
            tools.append(mcp_tool)
        agent = await stack.enter_async_context(
            Agent(
                client=client,
                name="DocumentOrchestrator",
                instructions=system,
                tools=tools,
            )
        )
        response = await agent.run(formatted_user)

    return MafAskResult(
        text=getattr(response, "text", None) or str(response),
        response_id=getattr(response, "response_id", None),
        raw=response,
        role=persona_label,
        persona=caller,
        prompt=user_text,
        version=str(validation.get("prompt_version") or None),
        authorized=True,
        validation=validation,
    )
