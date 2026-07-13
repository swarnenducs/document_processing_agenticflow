"""Optional agent mode: an LLM chooses which document tools to call."""

from __future__ import annotations

from typing import Any

from document_processing_agenticflow.tools import get_document_tools


SYSTEM_PROMPT = """You are a document processing agent.

Two separate LLMs power this pipeline:
- LLM #1 (Mapper, OpenAI): map_json_to_template — maps JSON → Word placeholders
- LLM #2 (Validator, Groq): validate_documents — critic checks output vs template + JSON

Tools:
1. load_json_data
2. extract_word_styles
3. map_json_to_template       ← LLM #1 (OpenAI)
4. generate_styled_document
5. validate_documents           ← LLM #2 (Groq critic)
6. compute_confidence_report

Typical order: load → extract → map → generate → validate → confidence.
Always report mapper LLM, validator LLM, overall_confidence, and any validation issues.
"""


def build_agent(model_name: str | None = None):
    """
    Build a tool-calling agent (orchestrator uses LLM #1 / OpenAI).
    Requires OPENAI_API_KEY. Returns a compiled LangGraph agent.
    """
    from langchain.agents import create_agent

    from document_processing_agenticflow.services.llm_factory import get_agent_llm, is_mapper_available

    if not is_mapper_available():
        raise RuntimeError("OPENAI_API_KEY is required for agent mode (LLM #1 orchestrator)")

    llm, config = get_agent_llm(model_name=model_name)
    tools = get_document_tools()
    prompt = SYSTEM_PROMPT + f"\nOrchestrator model: {config.label}"
    return create_agent(llm, tools, system_prompt=prompt)


def run_agent(user_message: str, model_name: str | None = None) -> Any:
    """Invoke the tool-calling agent with a natural-language instruction."""
    agent = build_agent(model_name=model_name)
    return agent.invoke({"messages": [{"role": "user", "content": user_message}]})
