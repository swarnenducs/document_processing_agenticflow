"""LangChain ChatPromptTemplate for MAF orchestrator turns."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


def orchestrator_chat_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "{system_instructions}"),
            ("human", "Persona: {persona}\n\n{message}"),
        ]
    )


def format_orchestrator_turn(
    *,
    system_instructions: str,
    message: str,
    persona: str = "analyst",
    version: str = "1",
    role: str | None = None,
) -> tuple[str, str]:
    """Return (system, human) strings formatted via ChatPromptTemplate."""
    _ = version
    messages = orchestrator_chat_prompt().format_messages(
        system_instructions=system_instructions,
        message=message,
        persona=role or persona,
    )
    if len(messages) < 2:
        raise RuntimeError("orchestrator ChatPromptTemplate must yield system + human")
    return str(messages[0].content), str(messages[1].content)
