"""Central factory for injectable LLMs — all chat models via LangChain ``init_chat_model``.

Roles
-----
- **mapper** (LLM #1): JSON → Word field / table mapping
- **validator** (LLM #2): independent critic
- **agent**: optional tool-calling orchestrator (defaults to mapper provider)

Switch any provider / model
---------------------------
Preferred (LangChain ``provider:model`` string → ``init_chat_model``)::

    MAPPER_MODEL_ID=azure_openai:gpt-5-mini
    VALIDATOR_MODEL_ID=groq:openai/gpt-oss-120b
    # Any init_chat_model provider works, e.g.:
    # MAPPER_MODEL_ID=anthropic:claude-sonnet-4-20250514
    # MAPPER_MODEL_ID=openai:gpt-4o
    # MAPPER_MODEL_ID=google_genai:gemini-2.0-flash

Or split vars still supported::

    MAPPER_PROVIDER=azure_openai
    MAPPER_MODEL=gpt-5-mini

Runtime override (code / LangGraph configurable)::

    get_mapper_llm(model_id="openai:gpt-4o-mini")
    init_role_chat_model("validator", model_id="anthropic:claude-sonnet-4-20250514")

    # LangGraph invoke:
    graph.invoke(state, config={"configurable": {
        "mapper_model_id": "openai:gpt-4o-mini",
        "validator_model_id": "groq:openai/gpt-oss-120b",
    }})

Custom / exotic SDKs::

    register_llm_provider("my_vendor", build_fn)
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

# builder(config, temperature) -> LangChain chat model
LLMProviderBuilder = Callable[["LLMRoleConfig", float], Any]

_PROVIDER_REGISTRY: dict[str, LLMProviderBuilder] = {}

# Optional per-role runtime overrides (provider:model) — set by LangGraph config / callers
_mapper_model_id_override: ContextVar[str | None] = ContextVar("mapper_model_id", default=None)
_validator_model_id_override: ContextVar[str | None] = ContextVar(
    "validator_model_id", default=None
)
_agent_model_id_override: ContextVar[str | None] = ContextVar("agent_model_id", default=None)


@dataclass(frozen=True)
class LLMRoleConfig:
    """Resolved provider/model settings for one LLM role."""

    role: str  # mapper | validator | agent
    provider: str  # openai | azure_openai | groq | anthropic | … | custom
    model: str
    label: str  # human-readable, e.g. "azure_openai/gpt-4o"
    api_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None
    temperature: float = 0.0
    extra: dict[str, str] | None = None


def register_llm_provider(name: str, builder: LLMProviderBuilder) -> None:
    """Register or replace a provider builder (injection point for other SDKs)."""
    key = name.strip().lower()
    if not key:
        raise ValueError("Provider name must be non-empty")
    _PROVIDER_REGISTRY[key] = builder


def unregister_llm_provider(name: str) -> None:
    """Remove a previously registered provider (mainly for tests)."""
    _PROVIDER_REGISTRY.pop(name.strip().lower(), None)


def list_llm_providers() -> list[str]:
    """Return documented + registered provider names (init_chat_model accepts more)."""
    built_in = {
        "openai",
        "azure_openai",
        "azure",
        "groq",
        "openai_compatible",
        "compatible",
        "anthropic",
        "google_genai",
        "google_vertexai",
        "mistralai",
        "fireworks",
        "together",
        "cohere",
        "bedrock",
        "huggingface",
        "ollama",
    }
    return sorted(built_in | set(_PROVIDER_REGISTRY))


def _env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _is_placeholder_value(value: str | None) -> bool:
    """True for empty or template placeholders left in .env."""
    if not value or not value.strip():
        return True
    lowered = value.strip().lower()
    markers = (
        "your_resource",
        "your-resource",
        "your_key",
        "your-key",
        "paste_your",
        "changeme",
        "placeholder",
        "example.openai.azure.com",
        "<",
    )
    return any(m in lowered for m in markers)


def _role_prefix(role: str) -> str:
    return role.upper()  # MAPPER / VALIDATOR / AGENT


def _normalize_provider(provider: str) -> str:
    p = provider.strip().lower()
    aliases = {
        "azure": "azure_openai",
        "aoai": "azure_openai",
        "azure-openai": "azure_openai",
        "compatible": "openai_compatible",
        "openai-compatible": "openai_compatible",
        "google": "google_genai",
        "gemini": "google_genai",
        "vertex": "google_vertexai",
        "claude": "anthropic",
    }
    return aliases.get(p, p)


def _default_provider(role: str) -> str:
    if role == "validator":
        return "groq"
    return "openai"


def _default_model(role: str, provider: str) -> str:
    if provider == "groq":
        return "openai/gpt-oss-120b"
    if provider == "azure_openai":
        return _env("AZURE_OPENAI_DEPLOYMENT") or _env("OPENAI_MODEL") or "gpt-4o"
    if provider == "anthropic":
        return "claude-sonnet-4-20250514"
    if provider in {"google_genai", "google_vertexai"}:
        return "gemini-2.0-flash"
    return "gpt-5"


def _resolve_model(role: str, provider: str) -> str:
    prefix = _role_prefix(role)
    role_model = _env(f"{prefix}_MODEL")
    if role_model:
        return role_model

    if role == "mapper":
        if provider == "azure_openai":
            return (
                _env("AZURE_OPENAI_DEPLOYMENT")
                or _env("OPENAI_MODEL")
                or _default_model(role, provider)
            )
        if provider == "groq":
            return _env("GROQ_MODEL") or _env("OPENAI_MODEL") or _default_model(role, provider)
        return _env("OPENAI_MODEL") or _default_model(role, provider)

    if role == "validator":
        if provider == "groq":
            return (
                _env("GROQ_VALIDATOR_MODEL")
                or _env("GROQ_MODEL")
                or _default_model(role, provider)
            )
        if provider == "azure_openai":
            return (
                _env("AZURE_OPENAI_VALIDATOR_DEPLOYMENT")
                or _env("AZURE_OPENAI_DEPLOYMENT")
                or _env("OPENAI_VALIDATOR_MODEL")
                or _env("OPENAI_MODEL")
                or _default_model(role, provider)
            )
        return (
            _env("OPENAI_VALIDATOR_MODEL")
            or _env("OPENAI_MODEL")
            or _default_model(role, provider)
        )

    # agent — inherit mapper model resolution unless AGENT_MODEL is set
    if _env("AGENT_MODEL"):
        return _env("AGENT_MODEL")  # type: ignore[return-value]
    return _resolve_model("mapper", provider)


def _resolve_api_key(role: str, provider: str) -> str | None:
    prefix = _role_prefix(role)
    role_key = _env(f"{prefix}_API_KEY")
    if role_key:
        return role_key

    if role == "agent":
        mapper_key = _env("MAPPER_API_KEY")
        if mapper_key:
            return mapper_key

    if provider == "openai":
        return _env("OPENAI_API_KEY")
    if provider == "azure_openai":
        return _env("AZURE_OPENAI_API_KEY")
    if provider == "groq":
        return _env("GROQ_API_KEY")
    if provider == "openai_compatible":
        return _env("OPENAI_API_KEY") or _env("COMPATIBLE_API_KEY")
    if provider == "anthropic":
        return _env("ANTHROPIC_API_KEY")
    if provider in {"google_genai", "google_vertexai"}:
        return _env("GOOGLE_API_KEY") or _env("GEMINI_API_KEY")
    if provider == "mistralai":
        return _env("MISTRAL_API_KEY")
    if provider == "fireworks":
        return _env("FIREWORKS_API_KEY")
    if provider == "together":
        return _env("TOGETHER_API_KEY")
    if provider == "cohere":
        return _env("COHERE_API_KEY")
    return None


def _resolve_base_url(role: str, provider: str) -> str | None:
    prefix = _role_prefix(role)
    role_url = _env(f"{prefix}_BASE_URL")
    if not role_url and role == "agent":
        role_url = _env("MAPPER_BASE_URL")

    candidates: list[str | None]
    if role_url:
        candidates = [role_url]
    elif provider == "openai":
        candidates = [_env("OPENAI_BASE_URL")]
    elif provider == "azure_openai":
        candidates = [_env("AZURE_OPENAI_ENDPOINT"), _env("AZURE_OPENAI_BASE_URL")]
    elif provider == "openai_compatible":
        candidates = [_env("OPENAI_BASE_URL"), _env("COMPATIBLE_BASE_URL")]
    elif provider == "groq":
        candidates = [_env("GROQ_BASE_URL")]
    elif provider == "ollama":
        candidates = [_env("OLLAMA_BASE_URL"), "http://127.0.0.1:11434"]
    else:
        candidates = []

    for raw in candidates:
        if raw and not _is_placeholder_value(raw):
            return raw.rstrip("/")
    return None


def _resolve_api_version(role: str, provider: str) -> str | None:
    if provider != "azure_openai":
        return _env(f"{_role_prefix(role)}_API_VERSION")
    return (
        _env(f"{_role_prefix(role)}_API_VERSION")
        or _env("AZURE_OPENAI_API_VERSION")
        or "2024-12-01-preview"
    )


def _resolve_temperature(role: str) -> float:
    raw = _env(f"{_role_prefix(role)}_TEMPERATURE") or _env("LLM_TEMPERATURE") or "0"
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse ``provider:model`` (model may contain ``/``, e.g. groq ids)."""
    raw = model_id.strip()
    if ":" not in raw:
        raise ValueError(
            f"MODEL_ID must look like 'provider:model', got {model_id!r}. "
            "Example: azure_openai:gpt-5-mini or groq:openai/gpt-oss-120b "
            "or anthropic:claude-sonnet-4-20250514"
        )
    provider_raw, _, model = raw.partition(":")
    provider = _normalize_provider(provider_raw)
    model = model.strip()
    if not provider or not model:
        raise ValueError(f"Invalid MODEL_ID {model_id!r}: empty provider or model")
    return provider, model


def _context_model_id(role: str) -> str | None:
    if role == "mapper":
        return _mapper_model_id_override.get()
    if role == "validator":
        return _validator_model_id_override.get()
    if role == "agent":
        return _agent_model_id_override.get()
    return None


def set_role_model_overrides(
    *,
    mapper_model_id: str | None = None,
    validator_model_id: str | None = None,
    agent_model_id: str | None = None,
) -> tuple[Token, Token, Token]:
    """Bind runtime ``provider:model`` overrides (e.g. from LangGraph configurable)."""
    return (
        _mapper_model_id_override.set(mapper_model_id),
        _validator_model_id_override.set(validator_model_id),
        _agent_model_id_override.set(agent_model_id),
    )


def reset_role_model_overrides(tokens: tuple[Token, Token, Token]) -> None:
    _mapper_model_id_override.reset(tokens[0])
    _validator_model_id_override.reset(tokens[1])
    _agent_model_id_override.reset(tokens[2])


def bind_model_overrides_from_config(config: dict[str, Any] | None) -> tuple[Token, Token, Token]:
    """Extract LangGraph ``configurable`` model ids and bind them."""
    configurable: dict[str, Any] = {}
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        if not isinstance(configurable, dict):
            configurable = {}
    return set_role_model_overrides(
        mapper_model_id=configurable.get("mapper_model_id")
        or configurable.get("mapper_model"),
        validator_model_id=configurable.get("validator_model_id")
        or configurable.get("validator_model"),
        agent_model_id=configurable.get("agent_model_id")
        or configurable.get("agent_model"),
    )


def resolve_role_config(
    role: str,
    *,
    model_override: str | None = None,
    model_id: str | None = None,
) -> LLMRoleConfig:
    """Resolve env → typed config for a role (mapper | validator | agent).

    Precedence for provider/model:
    1. Explicit ``model_id`` arg (``provider:model``)
    2. ContextVar override (LangGraph configurable)
    3. ``{ROLE}_MODEL_ID`` env
    4. Split ``{ROLE}_PROVIDER`` / ``{ROLE}_MODEL`` (+ legacy fallbacks)
    """
    role = role.strip().lower()
    if role not in {"mapper", "validator", "agent"}:
        raise ValueError(f"Unknown LLM role: {role}")

    prefix = _role_prefix(role)

    effective_model_id = (
        (model_id or "").strip()
        or (_context_model_id(role) or "").strip()
        or _env(f"{prefix}_MODEL_ID")
        or (_env("MAPPER_MODEL_ID") if role == "agent" else None)
    )

    if effective_model_id:
        provider, model_from_id = _parse_model_id(effective_model_id)
        model = model_override or model_from_id
    else:
        if role == "agent":
            provider_raw = (
                _env("AGENT_PROVIDER") or _env("MAPPER_PROVIDER") or _default_provider("mapper")
            )
        else:
            provider_raw = _env(f"{prefix}_PROVIDER") or _default_provider(role)
        provider = _normalize_provider(provider_raw)
        model = model_override or _resolve_model(role, provider)

    api_key = _resolve_api_key(role, provider)
    base_url = _resolve_base_url(role, provider)
    api_version = _resolve_api_version(role, provider)
    temperature = _resolve_temperature(role)

    return LLMRoleConfig(
        role=role,
        provider=provider,
        model=model,
        label=f"{provider}/{model}",
        api_key=api_key,
        base_url=base_url,
        api_version=api_version,
        temperature=temperature,
    )


def mapper_config(*, model_id: str | None = None) -> LLMRoleConfig:
    return resolve_role_config("mapper", model_id=model_id)


def validator_config(*, model_id: str | None = None) -> LLMRoleConfig:
    return resolve_role_config("validator", model_id=model_id)


def agent_config(*, model_name: str | None = None, model_id: str | None = None) -> LLMRoleConfig:
    return resolve_role_config("agent", model_override=model_name, model_id=model_id)


def config_model_id(config: LLMRoleConfig) -> str:
    """Return LangChain-style ``provider:model`` id for this role config."""
    return f"{_normalize_provider(config.provider)}:{config.model}"


# ---------------------------------------------------------------------------
# Builders — ALL built-ins go through LangChain init_chat_model
# ---------------------------------------------------------------------------


def _require_key(config: LLMRoleConfig, *, hint: str) -> str:
    if config.api_key:
        return config.api_key
    raise RuntimeError(
        f"{config.role} LLM ({config.provider}) needs an API key. Set "
        f"{config.role.upper()}_API_KEY or {hint}."
    )


def _normalize_azure_endpoint(endpoint: str) -> tuple[str, str]:
    """
    Return (style, base_url).

    - foundry_v1: Azure AI Foundry / ``*.services.ai.azure.com/.../openai/v1``
      → OpenAI-compatible path via init_chat_model(model_provider='openai')
    - classic: ``*.openai.azure.com`` → azure_openai provider
    """
    url = endpoint.strip().rstrip("/")
    for suffix in ("/responses", "/chat/completions", "/completions"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")

    if "services.ai.azure.com" in url.lower() or "/openai/v1" in url.lower():
        if not url.lower().endswith("/openai/v1"):
            url = f"{url}/openai/v1"
        return "foundry_v1", url
    return "classic", url


def _init_chat_model(*args: Any, **kwargs: Any) -> Any:
    """Lazy import — every chat LLM in this project goes through this helper."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(*args, **kwargs)


def _build_via_init_chat_model(config: LLMRoleConfig, temperature: float = 0) -> Any:
    """Construct a chat model using LangChain ``init_chat_model`` only."""
    provider = _normalize_provider(config.provider)
    model_id = config_model_id(config)
    temp = temperature

    # --- openai ---
    if provider == "openai":
        api_key = _require_key(config, hint="OPENAI_API_KEY")
        kwargs: dict[str, Any] = {"api_key": api_key, "temperature": temp}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return _init_chat_model(model_id, **kwargs)

    # --- groq ---
    if provider == "groq":
        api_key = _require_key(config, hint="GROQ_API_KEY")
        kwargs = {"api_key": api_key, "temperature": temp}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return _init_chat_model(model_id, **kwargs)

    # --- azure openai / foundry ---
    if provider == "azure_openai":
        api_key = _require_key(config, hint="AZURE_OPENAI_API_KEY")
        endpoint = config.base_url or _env("AZURE_OPENAI_ENDPOINT")
        if not endpoint or _is_placeholder_value(endpoint):
            raise RuntimeError(
                "Azure OpenAI requires a real AZURE_OPENAI_ENDPOINT "
                "(or MAPPER_BASE_URL / VALIDATOR_BASE_URL)."
            )
        style, base = _normalize_azure_endpoint(endpoint)

        # Foundry OpenAI v1 is OpenAI-compatible (not classic azure_openai kwargs).
        if style == "foundry_v1":
            kwargs = {"api_key": api_key, "base_url": base}
            if temp not in (None, 0, 0.0):
                kwargs["temperature"] = temp
            return _init_chat_model(f"openai:{config.model}", **kwargs)

        kwargs = {
            "api_key": api_key,
            "azure_endpoint": base,
            "api_version": config.api_version or "2024-12-01-preview",
            "temperature": temp,
        }
        return _init_chat_model(model_id, **kwargs)

    # --- openai-compatible / ollama ---
    if provider in {"openai_compatible", "ollama"}:
        base = config.base_url
        if provider == "ollama" and not base:
            base = "http://127.0.0.1:11434"
        if not base:
            raise RuntimeError(
                "openai_compatible / ollama requires a base URL "
                "(MAPPER_BASE_URL / OPENAI_BASE_URL / COMPATIBLE_BASE_URL / OLLAMA_BASE_URL)."
            )
        api_key = config.api_key or _env("OPENAI_API_KEY") or _env("COMPATIBLE_API_KEY") or "EMPTY"
        # Route through openai provider of init_chat_model + custom base_url
        return _init_chat_model(
            f"openai:{config.model}",
            api_key=api_key,
            base_url=base,
            temperature=temp,
        )

    # --- any other init_chat_model provider (anthropic, google_genai, mistralai, …) ---
    kwargs = {"temperature": temp}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url
    try:
        return _init_chat_model(model_id, **kwargs)
    except Exception as exc:
        known = ", ".join(list_llm_providers())
        raise ValueError(
            f"Failed to init_chat_model({model_id!r}) for role={config.role}. "
            f"Install the matching langchain integration package if needed. "
            f"Known/documented providers: {known}. "
            f"Or use register_llm_provider(...). Underlying error: {exc}"
        ) from exc


def _build_llm(config: LLMRoleConfig, temperature: float | None = None) -> Any:
    temp = config.temperature if temperature is None else temperature
    provider = _normalize_provider(config.provider)

    if provider in _PROVIDER_REGISTRY:
        return _PROVIDER_REGISTRY[provider](config, temp)

    return _build_via_init_chat_model(config, temp)


def _with_optional_structured(llm: Any, structured_schema: type[T] | None) -> Any:
    if structured_schema is None:
        return llm
    return llm.with_structured_output(structured_schema)


def init_role_chat_model(
    role: str,
    *,
    model_id: str | None = None,
    model_override: str | None = None,
    temperature: float | None = None,
    structured_schema: type[T] | None = None,
) -> tuple[Any, LLMRoleConfig]:
    """Public entry: build any role's chat model via ``init_chat_model``."""
    config = resolve_role_config(role, model_override=model_override, model_id=model_id)
    llm = _with_optional_structured(_build_llm(config, temperature), structured_schema)
    return llm, config


def get_mapper_llm(
    *,
    model_id: str | None = None,
    structured_schema: type[T] | None = None,
) -> tuple[Any, LLMRoleConfig]:
    """LLM #1 — mapping. Switch with ``MAPPER_MODEL_ID`` or ``model_id='provider:model'``."""
    return init_role_chat_model(
        "mapper", model_id=model_id, structured_schema=structured_schema
    )


def get_validator_llm(
    *,
    model_id: str | None = None,
    structured_schema: type[T] | None = None,
) -> tuple[Any, LLMRoleConfig]:
    """LLM #2 — critic. Switch with ``VALIDATOR_MODEL_ID`` or ``model_id='provider:model'``."""
    return init_role_chat_model(
        "validator", model_id=model_id, structured_schema=structured_schema
    )


def get_agent_llm(
    model_name: str | None = None,
    *,
    model_id: str | None = None,
) -> tuple[Any, LLMRoleConfig]:
    """Orchestrator agent LLM (defaults to mapper provider/settings)."""
    return init_role_chat_model(
        "agent", model_id=model_id, model_override=model_name
    )


def build_configurable_chat_model(
    *,
    default_model_id: str | None = None,
    temperature: float = 0,
) -> Any:
    """Return an ``init_chat_model`` instance with configurable provider/model fields.

    Switch at invoke time via LangGraph / Runnable config::

        model = build_configurable_chat_model(default_model_id="openai:gpt-4o-mini")
        model.invoke(messages, config={"configurable": {
            "model": "claude-sonnet-4-20250514",
            "model_provider": "anthropic",
        }})
    """
    kwargs: dict[str, Any] = {
        "temperature": temperature,
        "configurable_fields": ("model", "model_provider"),
    }
    if default_model_id:
        return _init_chat_model(default_model_id, **kwargs)
    return _init_chat_model(**kwargs)


def provider_credentials_available(config: LLMRoleConfig) -> bool:
    """Whether enough credentials exist to construct this role's LLM."""
    provider = _normalize_provider(config.provider)

    if provider in _PROVIDER_REGISTRY:
        return True

    if provider == "openai":
        return bool(config.api_key or _env("OPENAI_API_KEY"))
    if provider == "azure_openai":
        key = config.api_key or _env("AZURE_OPENAI_API_KEY")
        endpoint = config.base_url or _env("AZURE_OPENAI_ENDPOINT")
        return bool(key) and not _is_placeholder_value(key) and not _is_placeholder_value(endpoint)
    if provider == "groq":
        return bool(config.api_key or _env("GROQ_API_KEY"))
    if provider in {"openai_compatible", "ollama"}:
        return bool(
            config.base_url
            or _env("OPENAI_BASE_URL")
            or _env("COMPATIBLE_BASE_URL")
            or _env("OLLAMA_BASE_URL")
            or provider == "ollama"
        )
    if provider == "anthropic":
        return bool(config.api_key or _env("ANTHROPIC_API_KEY"))
    if provider in {"google_genai", "google_vertexai"}:
        return bool(config.api_key or _env("GOOGLE_API_KEY") or _env("GEMINI_API_KEY"))
    if provider == "mistralai":
        return bool(config.api_key or _env("MISTRAL_API_KEY"))
    # Unknown init_chat_model providers: allow attempt (package may use ADC / local auth)
    return True


def is_mapper_available() -> bool:
    return provider_credentials_available(resolve_role_config("mapper"))


def is_validator_available() -> bool:
    return provider_credentials_available(resolve_role_config("validator"))


def is_agent_available() -> bool:
    return provider_credentials_available(resolve_role_config("agent"))
