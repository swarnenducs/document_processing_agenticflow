"""Central factory for the two independent LLMs used in the pipeline.

LLM #1 (Mapper)  — OpenAI by default (e.g. gpt-5)
LLM #2 (Validator) — Groq by default (e.g. openai/gpt-oss-120b)

Configure via .env; each role has its own provider + model + API key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class LLMRoleConfig:
    """Resolved provider/model for one LLM role."""

    role: str  # mapper | validator
    provider: str  # openai | groq
    model: str
    label: str  # human-readable, e.g. "openai/gpt-5"


def _mapper_config() -> LLMRoleConfig:
    provider = os.getenv("MAPPER_PROVIDER", "openai").lower()
    model = os.getenv("OPENAI_MODEL", "gpt-5")
    return LLMRoleConfig(
        role="mapper",
        provider=provider,
        model=model,
        label=f"{provider}/{model}",
    )


def _validator_config() -> LLMRoleConfig:
    provider = os.getenv("VALIDATOR_PROVIDER", "groq").lower()
    if provider == "groq":
        model = os.getenv("GROQ_VALIDATOR_MODEL", "openai/gpt-oss-120b")
    else:
        model = os.getenv("OPENAI_VALIDATOR_MODEL") or os.getenv("OPENAI_MODEL", "gpt-5")
    return LLMRoleConfig(
        role="validator",
        provider=provider,
        model=model,
        label=f"{provider}/{model}",
    )


def mapper_config() -> LLMRoleConfig:
    """Return resolved config for LLM #1 (mapper)."""
    return _mapper_config()


def validator_config() -> LLMRoleConfig:
    """Return resolved config for LLM #2 (validator / critic)."""
    return _validator_config()


def _openai_llm(model: str, temperature: float = 0):
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI LLM calls")
    return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)


def _groq_llm(model: str, temperature: float = 0):
    from langchain_groq import ChatGroq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for Groq LLM calls")
    return ChatGroq(model=model, temperature=temperature, api_key=api_key)


def _build_llm(config: LLMRoleConfig, temperature: float = 0):
    if config.provider == "openai":
        return _openai_llm(config.model, temperature=temperature)
    if config.provider == "groq":
        return _groq_llm(config.model, temperature=temperature)
    raise ValueError(f"Unsupported LLM provider for {config.role}: {config.provider}")


def get_mapper_llm(*, structured_schema: type[T] | None = None) -> tuple[Any, LLMRoleConfig]:
    """
    LLM #1 — JSON → Word field mapping with structured output.
    Provider: MAPPER_PROVIDER (default openai) + OPENAI_MODEL.
    """
    config = _mapper_config()
    if config.provider != "openai":
        raise ValueError("Mapper currently supports MAPPER_PROVIDER=openai only")
    llm = _build_llm(config)
    if structured_schema is not None:
        llm = llm.with_structured_output(structured_schema)
    return llm, config


def get_validator_llm(*, structured_schema: type[T] | None = None) -> tuple[Any, LLMRoleConfig]:
    """
    LLM #2 — independent critic comparing template vs generated doc vs JSON.
    Provider: VALIDATOR_PROVIDER (default groq) + GROQ_VALIDATOR_MODEL or OPENAI_VALIDATOR_MODEL.
    """
    config = _validator_config()
    llm = _build_llm(config)
    if structured_schema is not None:
        llm = llm.with_structured_output(structured_schema)
    return llm, config


def get_agent_llm(model_name: str | None = None):
    """Orchestrator agent uses the mapper LLM (OpenAI) by default."""
    config = _mapper_config()
    model = model_name or config.model
    return _openai_llm(model), LLMRoleConfig(
        role="agent",
        provider="openai",
        model=model,
        label=f"openai/{model}",
    )


def is_mapper_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def is_validator_available() -> bool:
    config = _validator_config()
    if config.provider == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    if config.provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    return False
