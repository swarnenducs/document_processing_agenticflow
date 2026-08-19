"""MAF turns are formatted with LangChain ChatPromptTemplate."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from central_agentic_flow.chat_prompt import format_orchestrator_turn, orchestrator_chat_prompt


def test_orchestrator_prompt_is_chat_prompt_template() -> None:
    prompt = orchestrator_chat_prompt()
    assert isinstance(prompt, ChatPromptTemplate)
    assert "system_instructions" in prompt.input_variables
    assert "message" in prompt.input_variables


def test_format_orchestrator_turn_preserves_braces_in_system() -> None:
    system, human = format_orchestrator_turn(
        system_instructions="Call document_generate_document {not a template var}.",
        message="fill the template",
    )
    assert "document_generate_document" in system
    assert "{not a template var}" in system
    assert human == "fill the template"
