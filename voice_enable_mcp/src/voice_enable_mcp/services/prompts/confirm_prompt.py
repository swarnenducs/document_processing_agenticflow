"""Voice confirmation LLM prompts — YAML + LCEL."""

from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from voice_enable_mcp.prompts_loader import chat_prompt_from_yaml, load_prompt_yaml

_CONFIRM_YAML = "confirm.yml"


def get_confirm_system_prompt() -> str:
    return load_prompt_yaml(_CONFIRM_YAML)["system"]


def build_confirm_prompt() -> ChatPromptTemplate:
    return chat_prompt_from_yaml(_CONFIRM_YAML)


def build_confirm_chain(llm: Any) -> Any:
    """LCEL: ChatPromptTemplate | structured confirmation LLM."""
    return build_confirm_prompt() | llm
