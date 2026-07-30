"""Central factory for injectable LLMs used in the pipeline.

Roles
-----
- **mapper** (LLM #1): JSON → Word field / table mapping
- **validator** (LLM #2): independent critic
- **agent**: optional tool-calling orchestrator (defaults to mapper provider)

Model construction
------------------
Built-in providers are created via LangChain ``init_chat_model`` so provider +
model stay dynamic (``provider:model`` strings or role env vars). Custom
providers still use ``register_llm_provider(...)``.

Built-in providers
------------------
- ``openai`` — OpenAI Chat Completions
- ``azure_openai`` (alias ``azure``) — Azure OpenAI deployments / Foundry
- ``groq`` — Groq
- ``openai_compatible`` (alias ``compatible``) — any OpenAI-compatible
  HTTP API (Ollama, Together, vLLM, etc.) via ``base_url`` + API key

Inject a custom provider at runtime::

    from document_processing_agenticflow.services.llm_factory import register_llm_provider

    def build_my_llm(config, temperature=0):
        ...
        return chat_model

    register_llm_provider("my_provider", build_my_llm)
    # then set MAPPER_PROVIDER=my_provider

Environment (per role)
----------------------
Compact form (preferred for interviews / demos)::

    MAPPER_MODEL_ID=azure_openai:gpt-5-mini
    VALIDATOR_MODEL_ID=groq:openai/gpt-oss-120b

Or split vars (still supported)::

======= ========================= ==========================================
Role    Primary vars              Fallbacks
======= ========================= ==========================================
mapper  MAPPER_PROVIDER           default ``openai``
        MAPPER_MODEL              OPENAI_MODEL / AZURE_OPENAI_DEPLOYMENT / …
        MAPPER_MODEL_ID           ``provider:model`` overrides both above
        MAPPER_API_KEY            provider default key
        MAPPER_BASE_URL           OPENAI_BASE_URL / AZURE_OPENAI_ENDPOINT
        MAPPER_API_VERSION        AZURE_OPENAI_API_VERSION (Azure)
validator VALIDATOR_PROVIDER      default ``groq``
          VALIDATOR_MODEL         GROQ_VALIDATOR_MODEL / OPENAI_VALIDATOR_MODEL
          VALIDATOR_MODEL_ID      ``provider:model``
          VALIDATOR_API_KEY       …
          VALIDATOR_BASE_URL      …
          VALIDATOR_API_VERSION   …
======= ========================= ==========================================
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

# builder(config, temperature) -> LangChain chat model
LLMProviderBuilder = Callable[["LLMRoleConfig", float], Any]

_PROVIDER_REGISTRY: dict[str, LLMProviderBuilder] = {}


@dataclass(frozen=True)
class LLMRoleConfig:
    """Resolved provider/model settings for one LLM role."""

    role: str  # mapper | validator | agent
    provider: str  # openai | azure_openai | groq | openai_compatible | custom
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
    """Return built-in + registered provider names."""
    built_in = {"openai", "azure_openai", "azure", "groq", "openai_compatible", "compatible"}
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
        "ollama": "openai_compatible",
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
        # Do not fall back to OPENAI_API_KEY — that masks missing Azure config
        # and causes silent rule fallback when the Azure call fails.
        return _env("AZURE_OPENAI_API_KEY")
    if provider == "groq":
        return _env("GROQ_API_KEY")
    if provider == "openai_compatible":
        return _env("OPENAI_API_KEY") or _env("COMPATIBLE_API_KEY")
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
            "Example: azure_openai:gpt-5-mini or groq:openai/gpt-oss-120b"
        )
    provider_raw, _, model = raw.partition(":")
    provider = _normalize_provider(provider_raw)
    model = model.strip()
    if not provider or not model:
        raise ValueError(f"Invalid MODEL_ID {model_id!r}: empty provider or model")
    return provider, model


def resolve_role_config(role: str, *, model_override: str | None = None) -> LLMRoleConfig:
    """Resolve env → typed config for a role (mapper | validator | agent)."""
    role = role.strip().lower()
    if role not in {"mapper", "validator", "agent"}:
        raise ValueError(f"Unknown LLM role: {role}")

    prefix = _role_prefix(role)

    # Compact ``provider:model`` wins over split PROVIDER/MODEL when set.
    model_id = _env(f"{prefix}_MODEL_ID")
    if not model_id and role == "agent":
        model_id = _env("MAPPER_MODEL_ID")

    if model_id:
        provider, model_from_id = _parse_model_id(model_id)
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


def mapper_config() -> LLMRoleConfig:
    """Resolved config for LLM #1 (mapper)."""
    return resolve_role_config("mapper")


def validator_config() -> LLMRoleConfig:
    """Resolved config for LLM #2 (validator / critic)."""
    return resolve_role_config("validator")


def agent_config(*, model_name: str | None = None) -> LLMRoleConfig:
    """Resolved config for the optional agent orchestrator."""
    return resolve_role_config("agent", model_override=model_name)


def config_model_id(config: LLMRoleConfig) -> str:
    """Return LangChain-style ``provider:model`` id for this role config."""
    return f"{_normalize_provider(config.provider)}:{config.model}"


# ---------------------------------------------------------------------------
# Builders — built-ins go through init_chat_model
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
      → OpenAI-compatible ChatOpenAI via init_chat_model(model_provider='openai')
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


def _init_chat_model(**kwargs: Any) -> Any:
    """Lazy import wrapper so unit tests can import the factory without LangChain load cost."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(**kwargs)


def _build_via_init_chat_model(config: LLMRoleConfig, temperature: float = 0) -> Any:
    """Construct a built-in chat model using LangChain ``init_chat_model``."""
    provider = _normalize_provider(config.provider)

    if provider == "openai":
        api_key = _require_key(config, hint="OPENAI_API_KEY")
        kwargs: dict[str, Any] = {
            "model": config.model,
            "model_provider": "openai",
            "api_key": api_key,
            "temperature": temperature,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return _init_chat_model(**kwargs)

    if provider == "groq":
        api_key = _require_key(config, hint="GROQ_API_KEY")
        kwargs = {
            "model": config.model,
            "model_provider": "groq",
            "api_key": api_key,
            "temperature": temperature,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return _init_chat_model(**kwargs)

    if provider == "azure_openai":
        api_key = _require_key(config, hint="AZURE_OPENAI_API_KEY")
        endpoint = config.base_url or _env("AZURE_OPENAI_ENDPOINT")
        if not endpoint or _is_placeholder_value(endpoint):
            raise RuntimeError(
                "Azure OpenAI requires a real AZURE_OPENAI_ENDPOINT "
                "(or MAPPER_BASE_URL / VALIDATOR_BASE_URL)."
            )
        style, base = _normalize_azure_endpoint(endpoint)

        # Foundry OpenAI v1 route is OpenAI-compatible, not classic AzureChatOpenAI.
        if style == "foundry_v1":
            kwargs = {
                "model": config.model,
                "model_provider": "openai",
                "api_key": api_key,
                "base_url": base,
            }
            if temperature not in (None, 0, 0.0):
                kwargs["temperature"] = temperature
            return _init_chat_model(**kwargs)

        return _init_chat_model(
            model=config.model,
            model_provider="azure_openai",
            api_key=api_key,
            azure_endpoint=base,
            api_version=config.api_version or "2024-12-01-preview",
            temperature=temperature,
        )

    if provider == "openai_compatible":
        if not config.base_url:
            raise RuntimeError(
                "openai_compatible provider requires a base URL "
                "(MAPPER_BASE_URL / VALIDATOR_BASE_URL / OPENAI_BASE_URL / COMPATIBLE_BASE_URL)."
            )
        api_key = config.api_key or _env("OPENAI_API_KEY") or _env("COMPATIBLE_API_KEY") or "EMPTY"
        return _init_chat_model(
            model=config.model,
            model_provider="openai",
            api_key=api_key,
            base_url=config.base_url,
            temperature=temperature,
        )

    known = ", ".join(list_llm_providers())
    raise ValueError(
        f"Unsupported LLM provider for {config.role}: {config.provider!r}. "
        f"Known providers: {known}. "
        "Use register_llm_provider(...) to inject another."
    )


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


def get_mapper_llm(*, structured_schema: type[T] | None = None) -> tuple[Any, LLMRoleConfig]:
    """LLM #1 — mapping. Any registered/built-in provider via MAPPER_PROVIDER / MODEL_ID."""
    config = resolve_role_config("mapper")
    llm = _with_optional_structured(_build_llm(config), structured_schema)
    return llm, config


def get_validator_llm(*, structured_schema: type[T] | None = None) -> tuple[Any, LLMRoleConfig]:
    """LLM #2 — critic. Any registered/built-in provider via VALIDATOR_PROVIDER / MODEL_ID."""
    config = resolve_role_config("validator")
    llm = _with_optional_structured(_build_llm(config), structured_schema)
    return llm, config


def get_agent_llm(model_name: str | None = None) -> tuple[Any, LLMRoleConfig]:
    """Orchestrator agent LLM (defaults to mapper provider/settings)."""
    config = resolve_role_config("agent", model_override=model_name)
    return _build_llm(config), config


def provider_credentials_available(config: LLMRoleConfig) -> bool:
    """Whether enough credentials exist to construct this role's LLM."""
    provider = _normalize_provider(config.provider)

    if provider in _PROVIDER_REGISTRY:
        # Custom providers: treat role API key or any non-empty model as enough;
        # builder may still raise at call time.
        return True

    if provider == "openai":
        return bool(config.api_key or _env("OPENAI_API_KEY"))
    if provider == "azure_openai":
        key = config.api_key or _env("AZURE_OPENAI_API_KEY")
        endpoint = config.base_url or _env("AZURE_OPENAI_ENDPOINT")
        return bool(key) and not _is_placeholder_value(key) and not _is_placeholder_value(endpoint)
    if provider == "groq":
        return bool(config.api_key or _env("GROQ_API_KEY"))
    if provider == "openai_compatible":
        return bool(config.base_url or _env("OPENAI_BASE_URL") or _env("COMPATIBLE_BASE_URL"))
    return False


def is_mapper_available() -> bool:
    return provider_credentials_available(resolve_role_config("mapper"))


def is_validator_available() -> bool:
    return provider_credentials_available(resolve_role_config("validator"))


def is_agent_available() -> bool:
    return provider_credentials_available(resolve_role_config("agent"))
