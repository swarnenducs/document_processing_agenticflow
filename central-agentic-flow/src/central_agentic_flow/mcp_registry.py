"""MCP registry for the central agent — YAML config + optional env extras.

Primary source: ``central-agentic-flow/config/mcp_registry.yml``
(override with ``MAF_MCP_REGISTRY_FILE``).

Env still works for URL overrides and one-off extras::

    MAF_EXTRA_MCPS=fabric=http://127.0.0.1:8004/mcp
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

# Preferred hop names first; older names stay as aliases (existing .env still works).
_URL_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "TEMPLATE_PROCESSING_END_POINT": ("TEMPLATE_PROCESSING_END_POINT", "DOCUMENT_MCP_URL"),
    "DOCUMENT_MCP_URL": ("TEMPLATE_PROCESSING_END_POINT", "DOCUMENT_MCP_URL"),
    "VOICE_PROCESSING_END_POINT": ("VOICE_PROCESSING_END_POINT", "VOICE_MCP_URL"),
    "VOICE_MCP_URL": ("VOICE_PROCESSING_END_POINT", "VOICE_MCP_URL"),
    "CHAT_MCP_END_POINT": ("CHAT_MCP_END_POINT", "CHAT_MCP_URL"),
    "CHAT_MCP_URL": ("CHAT_MCP_END_POINT", "CHAT_MCP_URL"),
    "METADATA_EXTRACTION_END_POINT": (
        "METADATA_EXTRACTION_END_POINT",
        "METADATA_MCP_URL",
    ),
    "METADATA_MCP_URL": ("METADATA_EXTRACTION_END_POINT", "METADATA_MCP_URL"),
}

_registry_cache: list[McpServerSpec] | None = None
_registry_mtime: float | None = None
_registry_path: Path | None = None
_registry_fingerprint: str | None = None


@dataclass(frozen=True)
class McpToolRule:
    name: str
    when: str = ""
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpServerSpec:
    name: str
    url: str
    prefix: str
    description: str = ""
    enabled: bool = True
    invoke_modes: tuple[str, ...] = ("ask", "jobs")
    default_tool: str | None = None
    instructions: str = ""
    tools: tuple[McpToolRule, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    key: str | None = None

    @property
    def mcp_key(self) -> str:
        if self.key:
            return self.key
        slug = self.name.replace("-", "_")
        if slug in {"document", "voice"}:
            return f"{slug}_process_mcp"
        return f"{slug}_mcp"

    def allows_ask(self) -> bool:
        return "ask" in self.invoke_modes

    def allows_jobs(self) -> bool:
        return "jobs" in self.invoke_modes or "invoke" in self.invoke_modes

    def tool_rule(self, tool_name: str) -> McpToolRule | None:
        for rule in self.tools:
            if rule.name == tool_name:
                return rule
        return None


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


def document_mcp_url() -> str:
    """MAF → document MCP. ``TEMPLATE_PROCESSING_END_POINT`` then ``DOCUMENT_MCP_URL``."""
    return (
        _env(
            "TEMPLATE_PROCESSING_END_POINT",
            "DOCUMENT_MCP_URL",
            default="http://127.0.0.1:8001/mcp",
        )
        or ""
    ).rstrip("/")


def voice_mcp_url() -> str:
    """MAF → voice MCP. ``VOICE_PROCESSING_END_POINT`` then ``VOICE_MCP_URL``."""
    return (
        _env(
            "VOICE_PROCESSING_END_POINT",
            "VOICE_MCP_URL",
            default="http://127.0.0.1:8002/mcp",
        )
        or ""
    ).rstrip("/")


def business_mcp_url() -> str:
    """Chat-path MCP. Empty until a business MCP is configured."""
    return (_env("BUSINESS_MCP_URL", default="") or "").rstrip("/")


def chat_mcp_url() -> str:
    """Optional ask-mode chat MCP. ``CHAT_MCP_END_POINT`` then ``CHAT_MCP_URL``.

    Sibling of ``BUSINESS_MCP_URL`` — both can be set. Empty until configured.
    """
    return (
        _env("CHAT_MCP_END_POINT", "CHAT_MCP_URL", default="") or ""
    ).rstrip("/")


def metadata_mcp_url() -> str:
    """Optional jobs-mode metadata MCP. ``METADATA_EXTRACTION_END_POINT`` then
    ``METADATA_MCP_URL``. Empty until configured.
    """
    return (
        _env(
            "METADATA_EXTRACTION_END_POINT",
            "METADATA_MCP_URL",
            default="",
        )
        or ""
    ).rstrip("/")


def _component_root() -> Path:
    return Path(__file__).resolve().parents[2]


def registry_file() -> Path:
    override = _clean(os.getenv("MAF_MCP_REGISTRY_FILE"))
    if override:
        return Path(override).expanduser().resolve()
    return (_component_root() / "config" / "mcp_registry.yml").resolve()


def expand_env(text: str) -> str:
    """Replace ``${VAR}`` and ``${VAR:-default}``.

    Document/voice/chat/metadata MCP URL vars share an alias chain so YAML
    ``${DOCUMENT_MCP_URL}`` still picks up ``TEMPLATE_PROCESSING_END_POINT``
    (and the reverse). Same for chat and metadata preferred/alias pairs.
    """

    def _repl(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        for candidate in _URL_ENV_ALIASES.get(name, (name,)):
            value = os.getenv(candidate)
            if value is not None and value != "":
                return value
        if default is not None:
            return default
        return match.group(0)

    return _ENV_PATTERN.sub(_repl, text)


def _read_instructions_file(raw: str, *, base: Path) -> str:
    from central_agentic_flow.prompt_catalog import load_named_prompt
    from central_agentic_flow.prompt_versions import logical_prompt_name

    key = logical_prompt_name(raw)
    try:
        return load_named_prompt(key).body
    except (KeyError, FileNotFoundError, ValueError):
        pass
    path = Path(raw).expanduser()
    if not path.is_file():
        for folder in (base, _component_root() / "prompts", _component_root() / "config"):
            candidate = folder / raw
            if candidate.is_file():
                path = candidate
                break
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        text = "\n".join(lines[1:]).strip()
    return text


def _parse_tool_rules(raw: Any) -> tuple[McpToolRule, ...]:
    if not isinstance(raw, dict):
        return ()
    rules: list[McpToolRule] = []
    for name, body in raw.items():
        if not isinstance(name, str):
            continue
        data = body if isinstance(body, dict) else {}
        request = data.get("request") if isinstance(data.get("request"), dict) else {}
        required = tuple(str(x) for x in (request.get("required") or []) if x)
        optional = tuple(str(x) for x in (request.get("optional") or []) if x)
        rules.append(
            McpToolRule(
                name=name.strip(),
                when=str(data.get("when") or "").strip(),
                required=required,
                optional=optional,
            )
        )
    return tuple(rules)


def _spec_from_mapping(item: dict[str, Any], *, base: Path) -> McpServerSpec | None:
    name = str(item.get("name") or "").strip().lower()
    if not name:
        return None
    enabled = item.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return None
    url = expand_env(str(item.get("url") or "")).strip().rstrip("/")
    if not url:
        return None
    prefix = str(item.get("prefix") or name).strip() or name
    description = str(item.get("description") or f"{name} MCP").strip()
    invoke = item.get("invoke") if isinstance(item.get("invoke"), dict) else {}
    modes_raw = invoke.get("modes") or item.get("modes") or ["ask", "jobs"]
    if isinstance(modes_raw, str):
        modes = tuple(p.strip().lower() for p in modes_raw.split(",") if p.strip())
    else:
        modes = tuple(str(m).strip().lower() for m in modes_raw if str(m).strip())
    default_tool = str(invoke.get("default_tool") or item.get("default_tool") or "").strip() or None
    instructions = str(item.get("instructions") or "").strip()
    inst_file = str(item.get("instructions_file") or "").strip()
    if inst_file:
        file_text = _read_instructions_file(inst_file, base=base)
        instructions = "\n\n".join(p for p in (instructions, file_text) if p)
    tools = _parse_tool_rules(invoke.get("tools") or item.get("tools"))
    raw_aliases = item.get("aliases") or []
    if isinstance(raw_aliases, str):
        aliases = tuple(p.strip().lower() for p in raw_aliases.split(",") if p.strip())
    else:
        aliases = tuple(str(a).strip().lower() for a in raw_aliases if str(a).strip())
    env_url: str | None = None
    if name in {"contract-autocreation-mcp", "document"} or any(
        a in {"document", "template-auto-creation"} for a in aliases
    ):
        env_url = _env("TEMPLATE_PROCESSING_END_POINT", "DOCUMENT_MCP_URL")
    elif name in {"voice-agent", "voice"} or "voice" in aliases:
        env_url = _env("VOICE_PROCESSING_END_POINT", "VOICE_MCP_URL")
    elif name in {"chat-agent", "chat"} or "chat" in aliases:
        env_url = _env("CHAT_MCP_END_POINT", "CHAT_MCP_URL")
    elif name in {"metadata-agent", "metadata"} or "metadata" in aliases:
        env_url = _env("METADATA_EXTRACTION_END_POINT", "METADATA_MCP_URL")
    if env_url:
        url = env_url.rstrip("/")
    key = str(item.get("mcp") or item.get("key") or "").strip() or None
    prefix_safe = prefix.replace("-", "_") if "-" in prefix else prefix
    return McpServerSpec(
        name=name,
        url=url,
        prefix=prefix_safe,
        description=description,
        enabled=True,
        invoke_modes=modes or ("ask", "jobs"),
        default_tool=default_tool,
        instructions=instructions,
        tools=tools,
        aliases=aliases,
        key=key,
    )


def load_registry_yaml(path: Path | None = None) -> list[McpServerSpec]:
    target = path or registry_file()
    if not target.is_file():
        return []
    import yaml

    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return []
    servers = payload.get("servers") or []
    if not isinstance(servers, list):
        return []
    base = target.parent
    out: list[McpServerSpec] = []
    for item in servers:
        if not isinstance(item, dict):
            continue
        spec = _spec_from_mapping(item, base=base)
        if spec is not None:
            out.append(spec)
    return out


def orchestrator_preamble_from_yaml(path: Path | None = None) -> str | None:
    target = path or registry_file()
    if not target.is_file():
        return None
    import yaml

    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return None
    orch = payload.get("orchestrator") if isinstance(payload.get("orchestrator"), dict) else {}
    inst_file = str(orch.get("instructions_file") or "").strip()
    if not inst_file:
        return None
    text = _read_instructions_file(inst_file, base=target.parent)
    return text or None


def _builtin_servers() -> list[McpServerSpec]:
    return [
        McpServerSpec(
            name="contract-autocreation-mcp",
            url=document_mcp_url(),
            prefix="document",
            description="Template auto-creation — fill a Word .docx from JSON (LangGraph pipeline).",
            invoke_modes=("jobs",),
            default_tool="generate_document",
            aliases=("document", "template-auto-creation"),
            key="contract_autocreation_mcp",
        ),
        McpServerSpec(
            name="voice-agent",
            url=voice_mcp_url(),
            prefix="voice",
            description="Voice agent — spoken/typed create-contract with human-in-the-loop confirm.",
            invoke_modes=("jobs",),
            default_tool="start_voice_contract",
            aliases=("voice",),
            key="voice_process_mcp",
        ),
        *(
            [
                McpServerSpec(
                    name="business-agent",
                    url=business_mcp_url(),
                    prefix="business",
                    description="Business prompt responses — domain question answering for chat.",
                    invoke_modes=("ask",),
                    aliases=("business",),
                    key="business_process_mcp",
                )
            ]
            if business_mcp_url()
            else []
        ),
        *(
            [
                McpServerSpec(
                    name="chat-agent",
                    url=chat_mcp_url(),
                    prefix="chat",
                    description="General chat MCP — conversational tools for /ask (not jobs).",
                    invoke_modes=("ask",),
                    aliases=("chat",),
                    key="chat_process_mcp",
                )
            ]
            if chat_mcp_url()
            else []
        ),
        *(
            [
                McpServerSpec(
                    name="metadata-agent",
                    url=metadata_mcp_url(),
                    prefix="metadata",
                    description="Metadata extraction — structured metadata from a document (jobs).",
                    invoke_modes=("jobs",),
                    default_tool="extract_metadata",
                    aliases=("metadata",),
                    key="metadata_process_mcp",
                )
            ]
            if metadata_mcp_url()
            else []
        ),
    ]


def _parse_json_servers(raw: str) -> list[McpServerSpec]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("MAF_MCP_SERVERS JSON must be a list")
    out: list[McpServerSpec] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        spec = _spec_from_mapping(item, base=registry_file().parent)
        if spec is not None:
            out.append(spec)
    return out


def _parse_kv_servers(raw: str) -> list[McpServerSpec]:
    out: list[McpServerSpec] = []
    for part in raw.split(","):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        name, url = chunk.split("=", 1)
        name = name.strip().lower()
        url = expand_env(url.strip()).rstrip("/")
        if not name or not url:
            continue
        desc_env = os.getenv(f"MAF_MCP_{name.upper()}_DESCRIPTION", "").strip()
        prefix_env = os.getenv(f"MAF_MCP_{name.upper()}_PREFIX", "").strip()
        out.append(
            McpServerSpec(
                name=name,
                url=url,
                prefix=prefix_env or name,
                description=desc_env or f"{name} MCP",
            )
        )
    return out


def extra_mcp_servers() -> list[McpServerSpec]:
    json_raw = _clean(os.getenv("MAF_MCP_SERVERS"))
    if json_raw and json_raw.startswith("["):
        return _parse_json_servers(json_raw)
    kv_raw = _clean(os.getenv("MAF_EXTRA_MCPS") or os.getenv("MAF_MCP_SERVERS"))
    if kv_raw:
        return _parse_kv_servers(kv_raw)
    return []


def _extras_fingerprint() -> str:
    return "|".join(
        [
            os.getenv("MAF_EXTRA_MCPS") or "",
            os.getenv("MAF_MCP_SERVERS") or "",
            os.getenv("TEMPLATE_PROCESSING_END_POINT") or "",
            os.getenv("DOCUMENT_MCP_URL") or "",
            os.getenv("VOICE_PROCESSING_END_POINT") or "",
            os.getenv("VOICE_MCP_URL") or "",
            os.getenv("BUSINESS_MCP_URL") or "",
            os.getenv("CHAT_MCP_END_POINT") or "",
            os.getenv("CHAT_MCP_URL") or "",
            os.getenv("METADATA_EXTRACTION_END_POINT") or "",
            os.getenv("METADATA_MCP_URL") or "",
            os.getenv("MAF_MCP_REGISTRY_FILE") or "",
        ]
    )


def load_mcp_registry(*, force: bool = False) -> list[McpServerSpec]:
    """YAML registry first, then env extras. Later entries with the same name win."""
    global _registry_cache, _registry_mtime, _registry_path, _registry_fingerprint
    path = registry_file()
    mtime = path.stat().st_mtime if path.is_file() else None
    fingerprint = _extras_fingerprint()
    if (
        not force
        and _registry_cache is not None
        and _registry_path == path
        and _registry_mtime == mtime
        and _registry_fingerprint == fingerprint
    ):
        return list(_registry_cache)

    by_name: dict[str, McpServerSpec] = {}
    yaml_specs = load_registry_yaml(path)
    fallback = _builtin_servers() if not yaml_specs else []
    for spec in (*fallback, *yaml_specs, *extra_mcp_servers()):
        by_name[spec.name] = spec
    ordered = list(by_name.values())
    _registry_cache = ordered
    _registry_mtime = mtime
    _registry_path = path
    _registry_fingerprint = fingerprint
    return list(ordered)


def reset_mcp_registry() -> None:
    global _registry_cache, _registry_mtime, _registry_path, _registry_fingerprint
    _registry_cache = None
    _registry_mtime = None
    _registry_path = None
    _registry_fingerprint = None


def get_mcp_server(name: str) -> McpServerSpec:
    needle = (name or "").strip().lower()
    for spec in load_mcp_registry():
        if (
            spec.name == needle
            or spec.prefix == needle
            or spec.mcp_key == needle
            or needle in spec.aliases
        ):
            return spec
    raise KeyError(f"Unknown MCP server: {name}")


def resolve_server_and_tool(server: str | None, tool: str) -> tuple[McpServerSpec, str]:
    """Accept ``generate_document`` + server=document, or ``document_generate_document``."""
    raw_tool = (tool or "").strip()
    if not raw_tool:
        raise ValueError("tool is required")
    if server:
        spec = get_mcp_server(server)
        prefix = f"{spec.prefix}_"
        if raw_tool.startswith(prefix):
            return spec, raw_tool[len(prefix) :]
        return spec, raw_tool
    for spec in load_mcp_registry():
        prefix = f"{spec.prefix}_"
        if raw_tool.startswith(prefix):
            return spec, raw_tool[len(prefix) :]
    raise ValueError(
        "Pass server=document|voice|<extra> or a prefixed tool name "
        "(e.g. document_generate_document)"
    )


def assert_jobs_invoke(spec: McpServerSpec, tool_name: str) -> None:
    """Raise if YAML invoke rules forbid this /invoke call."""
    if not spec.allows_jobs():
        raise ValueError(
            f"MCP '{spec.name}' is not allowed for /invoke "
            f"(modes={list(spec.invoke_modes)})"
        )
    if tool_name == "health" or not spec.tools:
        return
    if spec.tool_rule(tool_name) is None:
        allowed = ", ".join(rule.name for rule in spec.tools)
        raise ValueError(
            f"Tool '{tool_name}' is not in invoke.tools for MCP '{spec.name}' "
            f"(allowed: {allowed})"
        )


def ask_mcp_servers() -> list[McpServerSpec]:
    return [spec for spec in load_mcp_registry() if spec.allows_ask()]


def spec_catalog_fields(spec: McpServerSpec) -> dict[str, Any]:
    return {
        "invoke": {
            "modes": list(spec.invoke_modes),
            "default_tool": spec.default_tool,
            "tools": [
                {
                    "name": rule.name,
                    "when": rule.when,
                    "required": list(rule.required),
                    "optional": list(rule.optional),
                }
                for rule in spec.tools
            ],
        }
    }


def build_agent_instructions(*, preamble: str) -> str:
    """Preamble (markdown) + per-MCP when/instructions from the YAML registry."""
    head = (preamble or "").strip() or "You are the document-processing orchestrator."
    blocks = [head.rstrip(), "", "## Registered MCP servers"]
    for spec in ask_mcp_servers():
        blocks.append("")
        blocks.append(f"### {spec.prefix}_*  ({spec.mcp_key})")
        if spec.description:
            blocks.append(spec.description)
        if spec.instructions:
            blocks.append(spec.instructions.strip())
        for rule in spec.tools:
            if rule.when:
                blocks.append(f"- `{spec.prefix}_{rule.name}`: {rule.when.strip()}")
    return "\n".join(blocks).strip() + "\n"
