"""Optional agent mode: an LLM chooses which document tools to call."""

from __future__ import annotations

from typing import Any

from document_processing_agenticflow.tools import get_document_tools


SYSTEM_PROMPT = """You are a document processing agent.

Two separate LLMs power this pipeline (providers are configurable via env):
- LLM #1 (Mapper): map_json_to_template — maps JSON → Word placeholders / table fills
- LLM #2 (Validator): validate_documents — critic checks output vs template + JSON

Tools:
1. load_json_data
2. extract_word_styles
3. map_json_to_template       ← LLM #1 (mapper provider)
4. generate_styled_document
5. validate_documents           ← LLM #2 (validator provider)
6. compute_confidence_report

Typical order: load → extract → map → generate → validate → confidence.
Always report mapper LLM, validator LLM, overall_confidence, and any validation issues.
"""


def build_agent(model_name: str | None = None):
    """
    Build a tool-calling agent (orchestrator uses the agent/mapper provider).
    Requires credentials for AGENT_PROVIDER / MAPPER_PROVIDER. Returns a compiled LangGraph agent.
    """
    from langchain.agents import create_agent

    from document_processing_agenticflow.services.llm_factory import get_agent_llm, is_agent_available

    if not is_agent_available():
        raise RuntimeError(
            "Agent mode needs credentials for AGENT_PROVIDER/MAPPER_PROVIDER "
            "(e.g. OPENAI_API_KEY, or AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT, or GROQ_API_KEY)."
        )

    llm, config = get_agent_llm(model_name=model_name)
    tools = get_document_tools()
    prompt = SYSTEM_PROMPT + f"\nOrchestrator model: {config.label}"
    return create_agent(llm, tools, system_prompt=prompt)


def run_agent(user_message: str, model_name: str | None = None) -> Any:
    """Invoke the tool-calling agent with a natural-language instruction."""
    agent = build_agent(model_name=model_name)
    return agent.invoke({"messages": [{"role": "user", "content": user_message}]})
