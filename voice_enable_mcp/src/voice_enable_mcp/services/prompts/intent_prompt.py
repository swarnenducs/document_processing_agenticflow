"""Voice intent LLM prompts — YAML + LCEL."""

from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from voice_enable_mcp.prompts_loader import chat_prompt_from_yaml, load_prompt_yaml

_INTENT_YAML = "intent.yml"


def get_intent_system_prompt() -> str:
    return load_prompt_yaml(_INTENT_YAML)["system"]


def build_intent_prompt() -> ChatPromptTemplate:
    return chat_prompt_from_yaml(_INTENT_YAML)


def build_intent_chain(llm: Any) -> Any:
    """LCEL: ChatPromptTemplate | structured voice-intent LLM."""
    return build_intent_prompt() | llm
